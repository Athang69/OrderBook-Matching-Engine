// Limit order book for one stock, matched by price-time priority.
//
// Layout:
//   * Prices are integers in paise, so Rs 1,402.50 is 140250. No floating point.
//   * The daily price band bounds the price range, so every valid price maps to a
//     slot in a flat array: slot = (price - lower_band) / tick.
//   * Each slot holds a first-in-first-out queue of orders (a doubly linked list
//     threaded through a preallocated pool), which gives time priority.
//   * A hash map from order id to pool slot makes cancel a direct lookup.
#pragma once

#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace ob {

using Price = std::int64_t;  // paise
using Qty = std::uint32_t;
using OrderId = std::uint64_t;

enum class Side : std::uint8_t { Buy, Sell };
enum class OrderType : std::uint8_t { Limit, Market };

enum class Reject : std::uint8_t {
    None,
    BadQuantity,
    BadTick,
    OutsideBand,
    DuplicateOrder,
    UnknownOrder,
    UnknownSymbol,
};

const char* to_string(Reject reason);

struct Trade {
    OrderId buy_id;
    OrderId sell_id;
    Price price;  // always the price of the order that was already waiting
    Qty qty;
};

struct LevelView {
    Price price;
    std::uint64_t qty;
    std::uint32_t orders;
};

struct Result {
    Reject reject = Reject::None;
    Qty filled = 0;     // traded immediately
    Qty resting = 0;    // left waiting in the book (limit orders only)
    Qty cancelled = 0;  // unfilled remainder of a market order
};

class OrderBook {
public:
    // lower_band and upper_band must be multiples of tick.
    OrderBook(Price tick, Price lower_band, Price upper_band);

    // Matches the order against the opposite side, then rests any limit remainder.
    // Trades are appended to `trades` in the order they happen.
    Result add(OrderId id, Side side, OrderType type, Price price, Qty qty, std::vector<Trade>& trades);

    // Removes a resting order. Returns the quantity removed, or 0 if it is not in the book.
    Qty cancel(OrderId id);

    bool contains(OrderId id) const { return index_.find(id) != index_.end(); }

    // Best `max_levels` price levels of one side, best price first.
    void depth(Side side, std::size_t max_levels, std::vector<LevelView>& out) const;

    bool best_bid(Price& price) const;
    bool best_ask(Price& price) const;

    std::size_t open_orders() const { return index_.size(); }
    Price tick() const { return tick_; }
    Price lower_band() const { return lower_; }
    Price upper_band() const { return upper_; }

private:
    static constexpr std::uint32_t NIL = 0xFFFFFFFFu;

    struct Node {
        OrderId id;
        Qty qty;
        std::uint32_t level;
        std::uint32_t prev;
        std::uint32_t next;
        Side side;
    };

    struct Level {
        std::uint64_t qty = 0;
        std::uint32_t head = NIL;
        std::uint32_t tail = NIL;
        std::uint32_t count = 0;
    };

    Price price_at(std::int64_t level) const { return lower_ + level * tick_; }
    std::uint32_t alloc_node();
    void push_back(std::vector<Level>& side, std::int64_t level, std::uint32_t node);
    void unlink(std::vector<Level>& side, std::uint32_t node);
    Qty match(OrderId taker, Side taker_side, std::int64_t limit_level, Qty qty, std::vector<Trade>& trades);

    Price tick_;
    Price lower_;
    Price upper_;
    std::int64_t levels_;

    std::vector<Level> bids_;
    std::vector<Level> asks_;
    std::int64_t best_bid_;  // -1 when there are no bids
    std::int64_t best_ask_;  // levels_ when there are no asks

    std::vector<Node> nodes_;
    std::uint32_t free_head_ = NIL;
    std::unordered_map<OrderId, std::uint32_t> index_;
};

}  // namespace ob
