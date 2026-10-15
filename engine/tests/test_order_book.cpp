// Unit tests for the order book, plus a randomised comparison against a slow,
// obviously-correct reference implementation.
#include <algorithm>
#include <cstdio>
#include <map>
#include <random>
#include <vector>

#include "ob/engine.hpp"
#include "ob/order_book.hpp"

using namespace ob;

namespace {

int failures = 0;
int checks = 0;

#define CHECK(cond)                                                                  \
    do {                                                                             \
        ++checks;                                                                    \
        if (!(cond)) {                                                               \
            ++failures;                                                              \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
        }                                                                            \
    } while (0)

// Tick of 5 paise, band Rs 90.00 to Rs 110.00.
OrderBook make_book() { return OrderBook(5, 9000, 11000); }

std::vector<LevelView> depth_of(const OrderBook& book, Side side, std::size_t n = 5) {
    std::vector<LevelView> out;
    book.depth(side, n, out);
    return out;
}

void test_limit_order_rests_when_nothing_matches() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    const Result r = book.add(1, Side::Buy, OrderType::Limit, 10000, 50, trades);
    CHECK(r.reject == Reject::None);
    CHECK(r.filled == 0 && r.resting == 50);
    CHECK(trades.empty());
    const auto bids = depth_of(book, Side::Buy);
    CHECK(bids.size() == 1 && bids[0].price == 10000 && bids[0].qty == 50 && bids[0].orders == 1);
    CHECK(depth_of(book, Side::Sell).empty());
}

void test_price_priority() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Sell, OrderType::Limit, 10010, 10, trades);
    book.add(2, Side::Sell, OrderType::Limit, 10000, 10, trades);  // better (lower) price, placed later
    book.add(3, Side::Buy, OrderType::Limit, 10010, 10, trades);
    CHECK(trades.size() == 1);
    CHECK(trades[0].sell_id == 2 && trades[0].buy_id == 3);
    CHECK(trades[0].price == 10000);  // trade happens at the waiting order's price
}

// The worked example from the project report.
void test_time_priority() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Sell, OrderType::Limit, 10000, 50, trades);  // A
    book.add(3, Side::Sell, OrderType::Limit, 10005, 40, trades);  // C
    book.add(2, Side::Sell, OrderType::Limit, 10000, 30, trades);  // B, same price as A but later
    const Result r = book.add(9, Side::Buy, OrderType::Limit, 10005, 70, trades);
    CHECK(r.filled == 70 && r.resting == 0);
    CHECK(trades.size() == 2);
    CHECK(trades[0].sell_id == 1 && trades[0].qty == 50 && trades[0].price == 10000);
    CHECK(trades[1].sell_id == 2 && trades[1].qty == 20 && trades[1].price == 10000);
    const auto asks = depth_of(book, Side::Sell);
    CHECK(asks.size() == 2);
    CHECK(asks[0].price == 10000 && asks[0].qty == 10 && asks[0].orders == 1);  // B keeps 10
    CHECK(asks[1].price == 10005 && asks[1].qty == 40);                         // C untouched
}

void test_partial_fill_then_rest() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Sell, OrderType::Limit, 10000, 60, trades);
    const Result r = book.add(2, Side::Buy, OrderType::Limit, 10000, 100, trades);
    CHECK(r.filled == 60 && r.resting == 40);
    Price bid = 0;
    Price ask = 0;
    CHECK(book.best_bid(bid) && bid == 10000);
    CHECK(!book.best_ask(ask));
}

void test_market_order_sweeps_levels() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Sell, OrderType::Limit, 10000, 80, trades);
    book.add(2, Side::Sell, OrderType::Limit, 10005, 120, trades);
    const Result r = book.add(3, Side::Buy, OrderType::Market, 0, 100, trades);
    CHECK(r.filled == 100 && r.resting == 0 && r.cancelled == 0);
    CHECK(trades.size() == 2);
    CHECK(trades[0].price == 10000 && trades[0].qty == 80);
    CHECK(trades[1].price == 10005 && trades[1].qty == 20);
    Price ask = 0;
    CHECK(book.best_ask(ask) && ask == 10005);
}

void test_market_order_remainder_is_cancelled() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Buy, OrderType::Limit, 9995, 30, trades);
    const Result r = book.add(2, Side::Sell, OrderType::Market, 0, 100, trades);
    CHECK(r.filled == 30 && r.cancelled == 70 && r.resting == 0);
    CHECK(book.open_orders() == 0);
    const Result empty = book.add(3, Side::Sell, OrderType::Market, 0, 10, trades);
    CHECK(empty.filled == 0 && empty.cancelled == 10);
}

void test_cancel() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    book.add(1, Side::Buy, OrderType::Limit, 10000, 50, trades);
    book.add(2, Side::Buy, OrderType::Limit, 9990, 20, trades);
    CHECK(book.cancel(1) == 50);
    CHECK(book.cancel(1) == 0);   // already gone
    CHECK(book.cancel(77) == 0);  // never existed
    Price bid = 0;
    CHECK(book.best_bid(bid) && bid == 9990);  // best bid moves down to the next level
    book.add(3, Side::Sell, OrderType::Limit, 9990, 20, trades);
    CHECK(book.cancel(2) == 0);  // fully filled, so nothing left to cancel
}

void test_rejects() {
    OrderBook book = make_book();
    std::vector<Trade> trades;
    CHECK(book.add(1, Side::Buy, OrderType::Limit, 10000, 0, trades).reject == Reject::BadQuantity);
    CHECK(book.add(1, Side::Buy, OrderType::Limit, 10002, 10, trades).reject == Reject::BadTick);
    CHECK(book.add(1, Side::Buy, OrderType::Limit, 8995, 10, trades).reject == Reject::OutsideBand);
    CHECK(book.add(1, Side::Sell, OrderType::Limit, 11005, 10, trades).reject == Reject::OutsideBand);
    CHECK(book.add(1, Side::Buy, OrderType::Limit, 10000, 10, trades).reject == Reject::None);
    CHECK(book.add(1, Side::Buy, OrderType::Limit, 10000, 10, trades).reject == Reject::DuplicateOrder);
    CHECK(trades.empty());
}

void test_engine_routes_by_symbol() {
    Engine engine;
    CHECK(engine.add_symbol("AAA", 5, 9000, 11000));
    CHECK(engine.add_symbol("BBB", 10, 50000, 60000));
    CHECK(engine.add_symbol("AAA", 5, 9000, 11000));   // an empty book takes a new day's band
    CHECK(!engine.add_symbol("BAD", 5, 9001, 11000));  // band not on the tick grid
    std::vector<Trade> trades;
    CHECK(engine.new_order(1, "ZZZ", Side::Buy, OrderType::Limit, 10000, 10, trades).reject == Reject::UnknownSymbol);
    CHECK(engine.new_order(1, "AAA", Side::Sell, OrderType::Limit, 10000, 10, trades).resting == 10);
    CHECK(!engine.add_symbol("AAA", 5, 9500, 10500));  // not while orders are resting in it
    CHECK(engine.new_order(1, "BBB", Side::Sell, OrderType::Limit, 55000, 10, trades).reject == Reject::DuplicateOrder);
    // The same price in another symbol must not match.
    CHECK(engine.new_order(2, "BBB", Side::Buy, OrderType::Limit, 55000, 10, trades).resting == 10);
    CHECK(trades.empty());
    CHECK(engine.new_order(3, "AAA", Side::Buy, OrderType::Limit, 10000, 10, trades).filled == 10);
    CHECK(engine.cancel(1) == 0);   // filled, so nothing to cancel
    CHECK(engine.cancel(2) == 10);
}

// ---- Randomised comparison with a slow reference book ----

struct RefOrder {
    OrderId id;
    Side side;
    Price price;
    Qty qty;
    std::uint64_t seq;
};

class RefBook {
public:
    Qty add(OrderId id, Side side, OrderType type, Price price, Qty qty, std::vector<Trade>& trades) {
        while (qty > 0) {
            // Best opposite order: best price, then earliest arrival.
            int best = -1;
            for (int i = 0; i < static_cast<int>(orders_.size()); ++i) {
                const RefOrder& o = orders_[i];
                if (o.side == side) continue;
                if (type == OrderType::Limit && (side == Side::Buy ? o.price > price : o.price < price)) continue;
                if (best < 0) { best = i; continue; }
                const RefOrder& b = orders_[best];
                const bool better_price = side == Side::Buy ? o.price < b.price : o.price > b.price;
                if (better_price || (o.price == b.price && o.seq < b.seq)) best = i;
            }
            if (best < 0) break;
            RefOrder& maker = orders_[best];
            const Qty fill = std::min(qty, maker.qty);
            trades.push_back(side == Side::Buy ? Trade{id, maker.id, maker.price, fill} : Trade{maker.id, id, maker.price, fill});
            qty -= fill;
            maker.qty -= fill;
            if (maker.qty == 0) orders_.erase(orders_.begin() + best);
        }
        if (qty > 0 && type == OrderType::Limit) orders_.push_back({id, side, price, qty, ++seq_});
        return qty;
    }

    Qty cancel(OrderId id) {
        for (auto it = orders_.begin(); it != orders_.end(); ++it) {
            if (it->id == id) {
                const Qty qty = it->qty;
                orders_.erase(it);
                return qty;
            }
        }
        return 0;
    }

    std::vector<LevelView> depth(Side side, std::size_t n) const {
        std::map<Price, LevelView> levels;
        for (const RefOrder& o : orders_) {
            if (o.side != side) continue;
            LevelView& l = levels[o.price];
            l.price = o.price;
            l.qty += o.qty;
            ++l.orders;
        }
        std::vector<LevelView> out;
        if (side == Side::Buy) {
            for (auto it = levels.rbegin(); it != levels.rend() && out.size() < n; ++it) out.push_back(it->second);
        } else {
            for (auto it = levels.begin(); it != levels.end() && out.size() < n; ++it) out.push_back(it->second);
        }
        return out;
    }

    std::vector<OrderId> ids() const {
        std::vector<OrderId> out;
        for (const RefOrder& o : orders_) out.push_back(o.id);
        return out;
    }

private:
    std::vector<RefOrder> orders_;
    std::uint64_t seq_ = 0;
};

bool same(const std::vector<LevelView>& a, const std::vector<LevelView>& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (a[i].price != b[i].price || a[i].qty != b[i].qty || a[i].orders != b[i].orders) return false;
    }
    return true;
}

void test_random_against_reference() {
    OrderBook book = make_book();
    RefBook ref;
    std::mt19937_64 rng(20261012);
    OrderId next_id = 1;
    int mismatches = 0;
    const int ops = 60000;
    for (int i = 0; i < ops && mismatches == 0; ++i) {
        const int roll = static_cast<int>(rng() % 100);
        if (roll < 30) {
            const auto live = ref.ids();
            const OrderId id = live.empty() ? 999999999 : live[rng() % live.size()];
            if (book.cancel(id) != ref.cancel(id)) ++mismatches;
        } else {
            const Side side = rng() % 2 ? Side::Buy : Side::Sell;
            const OrderType type = roll < 40 ? OrderType::Market : OrderType::Limit;
            const Price price = 9950 + 5 * static_cast<Price>(rng() % 21);  // Rs 99.50 to Rs 100.50
            const Qty qty = 1 + static_cast<Qty>(rng() % 200);
            std::vector<Trade> got;
            std::vector<Trade> want;
            const OrderId id = next_id++;
            const Result r = book.add(id, side, type, price, qty, got);
            const Qty left = ref.add(id, side, type, price, qty, want);
            if (r.reject != Reject::None || r.filled != qty - left || got.size() != want.size()) ++mismatches;
            for (std::size_t t = 0; t < got.size() && t < want.size(); ++t) {
                if (got[t].buy_id != want[t].buy_id || got[t].sell_id != want[t].sell_id ||
                    got[t].price != want[t].price || got[t].qty != want[t].qty) {
                    ++mismatches;
                }
            }
        }
        if (!same(depth_of(book, Side::Buy, 25), ref.depth(Side::Buy, 25))) ++mismatches;
        if (!same(depth_of(book, Side::Sell, 25), ref.depth(Side::Sell, 25))) ++mismatches;
    }
    CHECK(mismatches == 0);
    CHECK(book.open_orders() == ref.ids().size());
}

}  // namespace

int main() {
    test_limit_order_rests_when_nothing_matches();
    test_price_priority();
    test_time_priority();
    test_partial_fill_then_rest();
    test_market_order_sweeps_levels();
    test_market_order_remainder_is_cancelled();
    test_cancel();
    test_rejects();
    test_engine_routes_by_symbol();
    test_random_against_reference();
    std::printf("%d checks, %d failed\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
