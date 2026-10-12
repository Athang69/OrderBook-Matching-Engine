#include "ob/order_book.hpp"

#include <algorithm>
#include <stdexcept>

namespace ob {

const char* to_string(Reject reason) {
    switch (reason) {
        case Reject::None: return "NONE";
        case Reject::BadQuantity: return "BAD_QUANTITY";
        case Reject::BadTick: return "BAD_TICK";
        case Reject::OutsideBand: return "OUTSIDE_PRICE_BAND";
        case Reject::DuplicateOrder: return "DUPLICATE_ORDER";
        case Reject::UnknownOrder: return "UNKNOWN_ORDER";
        case Reject::UnknownSymbol: return "UNKNOWN_SYMBOL";
    }
    return "UNKNOWN";
}

OrderBook::OrderBook(Price tick, Price lower_band, Price upper_band)
    : tick_(tick), lower_(lower_band), upper_(upper_band) {
    if (tick <= 0 || lower_band <= 0 || upper_band < lower_band || lower_band % tick != 0 || upper_band % tick != 0) {
        throw std::invalid_argument("invalid tick size or price band");
    }
    levels_ = (upper_ - lower_) / tick_ + 1;
    bids_.resize(static_cast<std::size_t>(levels_));
    asks_.resize(static_cast<std::size_t>(levels_));
    best_bid_ = -1;
    best_ask_ = levels_;
    nodes_.reserve(1 << 16);
    index_.reserve(1 << 16);
}

std::uint32_t OrderBook::alloc_node() {
    if (free_head_ != NIL) {
        const std::uint32_t node = free_head_;
        free_head_ = nodes_[node].next;
        return node;
    }
    nodes_.emplace_back();
    return static_cast<std::uint32_t>(nodes_.size() - 1);
}

void OrderBook::push_back(std::vector<Level>& side, std::int64_t level, std::uint32_t node) {
    Level& lvl = side[static_cast<std::size_t>(level)];
    Node& n = nodes_[node];
    n.level = static_cast<std::uint32_t>(level);
    n.prev = lvl.tail;
    n.next = NIL;
    if (lvl.tail != NIL) {
        nodes_[lvl.tail].next = node;
    } else {
        lvl.head = node;
    }
    lvl.tail = node;
    lvl.qty += n.qty;
    ++lvl.count;
}

// Takes a node out of its price level and returns it to the free list.
void OrderBook::unlink(std::vector<Level>& side, std::uint32_t node) {
    Node& n = nodes_[node];
    Level& lvl = side[n.level];
    if (n.prev != NIL) {
        nodes_[n.prev].next = n.next;
    } else {
        lvl.head = n.next;
    }
    if (n.next != NIL) {
        nodes_[n.next].prev = n.prev;
    } else {
        lvl.tail = n.prev;
    }
    lvl.qty -= n.qty;
    --lvl.count;
    index_.erase(n.id);
    n.next = free_head_;
    free_head_ = node;
}

// Trades the taker against the opposite side, best price first and, within a
// price, earliest order first. Returns the quantity left untraded.
Qty OrderBook::match(OrderId taker, Side taker_side, std::int64_t limit_level, Qty qty, std::vector<Trade>& trades) {
    const bool buying = taker_side == Side::Buy;
    std::vector<Level>& book = buying ? asks_ : bids_;

    while (qty > 0) {
        const std::int64_t best = buying ? best_ask_ : best_bid_;
        const bool crosses = buying ? (best < levels_ && best <= limit_level) : (best >= 0 && best >= limit_level);
        if (!crosses) break;

        Level& lvl = book[static_cast<std::size_t>(best)];
        const Price price = price_at(best);
        while (qty > 0 && lvl.head != NIL) {
            const std::uint32_t maker_slot = lvl.head;
            Node& maker = nodes_[maker_slot];
            const Qty fill = std::min(qty, maker.qty);
            trades.push_back(buying ? Trade{taker, maker.id, price, fill} : Trade{maker.id, taker, price, fill});
            qty -= fill;
            if (fill == maker.qty) {
                unlink(book, maker_slot);
            } else {
                maker.qty -= fill;
                lvl.qty -= fill;
            }
        }
        if (lvl.head == NIL) {
            // This price is exhausted: move to the next price that has orders.
            if (buying) {
                while (best_ask_ < levels_ && asks_[static_cast<std::size_t>(best_ask_)].head == NIL) ++best_ask_;
            } else {
                while (best_bid_ >= 0 && bids_[static_cast<std::size_t>(best_bid_)].head == NIL) --best_bid_;
            }
        }
    }
    return qty;
}

Result OrderBook::add(OrderId id, Side side, OrderType type, Price price, Qty qty, std::vector<Trade>& trades) {
    Result result;
    if (qty == 0) {
        result.reject = Reject::BadQuantity;
        return result;
    }
    if (contains(id)) {
        result.reject = Reject::DuplicateOrder;
        return result;
    }

    std::int64_t limit_level;
    if (type == OrderType::Limit) {
        if (price < lower_ || price > upper_) {
            result.reject = Reject::OutsideBand;
            return result;
        }
        if (price % tick_ != 0) {
            result.reject = Reject::BadTick;
            return result;
        }
        limit_level = (price - lower_) / tick_;
    } else {
        // A market order accepts any price inside the band.
        limit_level = side == Side::Buy ? levels_ - 1 : 0;
    }

    const Qty remaining = match(id, side, limit_level, qty, trades);
    result.filled = qty - remaining;
    if (remaining == 0) return result;

    if (type == OrderType::Market) {
        result.cancelled = remaining;
        return result;
    }

    const std::uint32_t node = alloc_node();
    nodes_[node].id = id;
    nodes_[node].qty = remaining;
    nodes_[node].side = side;
    index_.emplace(id, node);
    if (side == Side::Buy) {
        push_back(bids_, limit_level, node);
        best_bid_ = std::max(best_bid_, limit_level);
    } else {
        push_back(asks_, limit_level, node);
        best_ask_ = std::min(best_ask_, limit_level);
    }
    result.resting = remaining;
    return result;
}

Qty OrderBook::cancel(OrderId id) {
    const auto it = index_.find(id);
    if (it == index_.end()) return 0;
    const std::uint32_t node = it->second;
    const Qty qty = nodes_[node].qty;
    if (nodes_[node].side == Side::Buy) {
        unlink(bids_, node);
        while (best_bid_ >= 0 && bids_[static_cast<std::size_t>(best_bid_)].head == NIL) --best_bid_;
    } else {
        unlink(asks_, node);
        while (best_ask_ < levels_ && asks_[static_cast<std::size_t>(best_ask_)].head == NIL) ++best_ask_;
    }
    return qty;
}

void OrderBook::depth(Side side, std::size_t max_levels, std::vector<LevelView>& out) const {
    if (side == Side::Buy) {
        for (std::int64_t lvl = best_bid_; lvl >= 0 && out.size() < max_levels; --lvl) {
            const Level& level = bids_[static_cast<std::size_t>(lvl)];
            if (level.count > 0) out.push_back({price_at(lvl), level.qty, level.count});
        }
    } else {
        for (std::int64_t lvl = best_ask_; lvl < levels_ && out.size() < max_levels; ++lvl) {
            const Level& level = asks_[static_cast<std::size_t>(lvl)];
            if (level.count > 0) out.push_back({price_at(lvl), level.qty, level.count});
        }
    }
}

bool OrderBook::best_bid(Price& price) const {
    if (best_bid_ < 0) return false;
    price = price_at(best_bid_);
    return true;
}

bool OrderBook::best_ask(Price& price) const {
    if (best_ask_ >= levels_) return false;
    price = price_at(best_ask_);
    return true;
}

}  // namespace ob
