// Holds one order book per stock and routes each request to the right book.
#pragma once

#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "ob/order_book.hpp"

namespace ob {

class Engine {
public:
    // Returns false if the symbol already exists or the configuration is invalid.
    bool add_symbol(const std::string& symbol, Price tick, Price lower_band, Price upper_band) {
        if (books_.count(symbol) != 0) return false;
        try {
            books_.emplace(symbol, std::make_unique<OrderBook>(tick, lower_band, upper_band));
        } catch (const std::invalid_argument&) {
            return false;
        }
        return true;
    }

    OrderBook* book(const std::string& symbol) {
        const auto it = books_.find(symbol);
        return it == books_.end() ? nullptr : it->second.get();
    }

    Result new_order(OrderId id, const std::string& symbol, Side side, OrderType type, Price price, Qty qty,
                     std::vector<Trade>& trades) {
        OrderBook* target = book(symbol);
        if (target == nullptr) {
            Result result;
            result.reject = Reject::UnknownSymbol;
            return result;
        }
        if (owner_.count(id) != 0) {
            Result result;
            result.reject = Reject::DuplicateOrder;
            return result;
        }
        const std::size_t first_trade = trades.size();
        const Result result = target->add(id, side, type, price, qty, trades);
        if (result.resting > 0) owner_.emplace(id, target);
        // Forget resting orders that this order filled completely.
        for (std::size_t i = first_trade; i < trades.size(); ++i) {
            const OrderId maker = side == Side::Buy ? trades[i].sell_id : trades[i].buy_id;
            if (!target->contains(maker)) owner_.erase(maker);
        }
        return result;
    }

    // Returns the quantity removed, or 0 if the order is not resting in any book.
    Qty cancel(OrderId id) {
        const auto it = owner_.find(id);
        if (it == owner_.end()) return 0;
        const Qty removed = it->second->cancel(id);
        owner_.erase(it);
        return removed;
    }

private:
    std::unordered_map<std::string, std::unique_ptr<OrderBook>> books_;
    std::unordered_map<OrderId, OrderBook*> owner_;  // which book a resting order lives in
};

}  // namespace ob
