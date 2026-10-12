// Speed test for the order book. Feeds a random mix of limit orders, market
// orders and cancels to one book and reports throughput and per-operation latency.
//
// Only the call into the book is timed; generating the random input is not.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <vector>

#include "ob/order_book.hpp"

using namespace ob;
using Clock = std::chrono::steady_clock;

namespace {

std::uint64_t percentile(const std::vector<std::uint32_t>& sorted, double p) {
    const std::size_t i = static_cast<std::size_t>(p * static_cast<double>(sorted.size() - 1));
    return sorted[i];
}

}  // namespace

int main(int argc, char** argv) {
    const std::size_t timed_ops = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 2'000'000;
    const std::size_t warmup_ops = 200'000;

    // Rs 1,000 stock, 5 paise tick, 10% band: 4,001 price levels.
    const Price tick = 5;
    const Price reference = 100'000;
    OrderBook book(tick, 90'000, 110'000);

    std::mt19937_64 rng(42);
    std::vector<OrderId> live;  // ids we believe are resting; some will already be filled
    live.reserve(1 << 20);
    std::vector<Trade> trades;
    trades.reserve(1024);
    std::vector<std::uint32_t> latency_ns;
    latency_ns.reserve(timed_ops);

    OrderId next_id = 1;
    std::uint64_t trade_count = 0;
    std::uint64_t new_orders = 0;
    std::uint64_t market_orders = 0;
    std::uint64_t cancels = 0;
    std::uint64_t cancel_misses = 0;
    std::uint64_t timed_ns = 0;

    for (std::size_t i = 0; i < warmup_ops + timed_ops; ++i) {
        const bool timed = i >= warmup_ops;
        const int roll = static_cast<int>(rng() % 100);
        Price bid = 0;
        Price ask = 0;
        const Price mid = book.best_bid(bid) && book.best_ask(ask) ? (bid + ask) / 2 : reference;
        trades.clear();

        if (roll < 40 && !live.empty()) {
            // Cancel a random order.
            const std::size_t pick = rng() % live.size();
            const OrderId id = live[pick];
            live[pick] = live.back();
            live.pop_back();
            const auto start = Clock::now();
            const Qty removed = book.cancel(id);
            const auto stop = Clock::now();
            if (timed) {
                const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
                latency_ns.push_back(static_cast<std::uint32_t>(ns));
                timed_ns += static_cast<std::uint64_t>(ns);
                ++cancels;
                if (removed == 0) ++cancel_misses;
            }
        } else {
            const Side side = rng() % 2 ? Side::Buy : Side::Sell;
            const bool market = roll >= 90;
            const Qty qty = 1 + static_cast<Qty>(rng() % 500);
            // Limit prices land within 20 ticks of the mid; about one in six crosses the spread.
            const Price offset = static_cast<Price>(rng() % 24) - 3;
            Price price = side == Side::Buy ? mid - offset * tick : mid + offset * tick;
            price = std::clamp(price - price % tick, book.lower_band(), book.upper_band());
            const OrderId id = next_id++;
            const auto start = Clock::now();
            const Result r = book.add(id, side, market ? OrderType::Market : OrderType::Limit, price, qty, trades);
            const auto stop = Clock::now();
            if (r.resting > 0) live.push_back(id);
            if (timed) {
                const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
                latency_ns.push_back(static_cast<std::uint32_t>(ns));
                timed_ns += static_cast<std::uint64_t>(ns);
                trade_count += trades.size();
                if (market) ++market_orders; else ++new_orders;
            }
        }
    }

    std::sort(latency_ns.begin(), latency_ns.end());
    const double seconds = static_cast<double>(timed_ns) / 1e9;
    std::printf("operations timed     : %zu\n", latency_ns.size());
    std::printf("  limit orders       : %llu\n", static_cast<unsigned long long>(new_orders));
    std::printf("  market orders      : %llu\n", static_cast<unsigned long long>(market_orders));
    std::printf("  cancels            : %llu (%llu already filled)\n", static_cast<unsigned long long>(cancels),
                static_cast<unsigned long long>(cancel_misses));
    std::printf("trades produced      : %llu\n", static_cast<unsigned long long>(trade_count));
    std::printf("orders left in book  : %zu\n", book.open_orders());
    std::printf("throughput           : %.2f million operations per second\n", static_cast<double>(latency_ns.size()) / seconds / 1e6);
    std::printf("latency per operation: median %llu ns, p99 %llu ns, p99.9 %llu ns, max %llu ns\n",
                static_cast<unsigned long long>(percentile(latency_ns, 0.50)),
                static_cast<unsigned long long>(percentile(latency_ns, 0.99)),
                static_cast<unsigned long long>(percentile(latency_ns, 0.999)),
                static_cast<unsigned long long>(latency_ns.back()));
    std::printf("(each latency includes about 20-40 ns of clock overhead)\n");
    return 0;
}
