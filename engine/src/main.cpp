// Matching engine process. Reads one command per line on stdin and writes the
// resulting events on stdout, ending every reply with a line "END".
//
//   SYM <symbol> <tick> <lower_band> <upper_band>     -> OK | ERR <reason>  (adds a stock, or resets an empty book)
//   NEW <id> <symbol> <B|S> <L|M> <price> <qty>       -> REJ <id> <reason>
//                                                      | ACK <id>, TRD <buy_id> <sell_id> <price> <qty>...,
//                                                        FIN <id> <filled> <resting> <cancelled>
//   CXL <id>                                          -> CXD <id> <qty> | REJ <id> UNKNOWN_ORDER
//   DEP <symbol> <levels>                             -> BID <price> <qty> <orders>..., ASK <price> <qty> <orders>...
//   PING                                              -> PONG
//
// Prices are integers in paise. The process is single threaded, so commands are
// applied strictly in the order they arrive.
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "ob/engine.hpp"

namespace {

void handle(ob::Engine& engine, const std::string& line, std::ostream& out) {
    std::istringstream in(line);
    std::string cmd;
    in >> cmd;

    if (cmd == "NEW") {
        ob::OrderId id = 0;
        std::string symbol;
        char side = 0;
        char type = 0;
        ob::Price price = 0;
        long long qty = 0;
        in >> id >> symbol >> side >> type >> price >> qty;
        if (!in || (side != 'B' && side != 'S') || (type != 'L' && type != 'M') || qty < 0 || qty > 0xFFFFFFFFLL) {
            out << "ERR malformed NEW\n";
            return;
        }
        std::vector<ob::Trade> trades;
        const ob::Result result = engine.new_order(id, symbol, side == 'B' ? ob::Side::Buy : ob::Side::Sell,
                                                   type == 'L' ? ob::OrderType::Limit : ob::OrderType::Market, price,
                                                   static_cast<ob::Qty>(qty), trades);
        if (result.reject != ob::Reject::None) {
            out << "REJ " << id << ' ' << ob::to_string(result.reject) << '\n';
            return;
        }
        out << "ACK " << id << '\n';
        for (const ob::Trade& t : trades) {
            out << "TRD " << t.buy_id << ' ' << t.sell_id << ' ' << t.price << ' ' << t.qty << '\n';
        }
        out << "FIN " << id << ' ' << result.filled << ' ' << result.resting << ' ' << result.cancelled << '\n';
    } else if (cmd == "CXL") {
        ob::OrderId id = 0;
        in >> id;
        if (!in) {
            out << "ERR malformed CXL\n";
            return;
        }
        const ob::Qty removed = engine.cancel(id);
        if (removed == 0) {
            out << "REJ " << id << ' ' << ob::to_string(ob::Reject::UnknownOrder) << '\n';
        } else {
            out << "CXD " << id << ' ' << removed << '\n';
        }
    } else if (cmd == "DEP") {
        std::string symbol;
        std::size_t levels = 0;
        in >> symbol >> levels;
        ob::OrderBook* book = in ? engine.book(symbol) : nullptr;
        if (book == nullptr) {
            out << "ERR unknown symbol\n";
            return;
        }
        std::vector<ob::LevelView> view;
        book->depth(ob::Side::Buy, levels, view);
        for (const ob::LevelView& l : view) out << "BID " << l.price << ' ' << l.qty << ' ' << l.orders << '\n';
        view.clear();
        book->depth(ob::Side::Sell, levels, view);
        for (const ob::LevelView& l : view) out << "ASK " << l.price << ' ' << l.qty << ' ' << l.orders << '\n';
    } else if (cmd == "SYM") {
        std::string symbol;
        ob::Price tick = 0;
        ob::Price lower = 0;
        ob::Price upper = 0;
        in >> symbol >> tick >> lower >> upper;
        if (!in || !engine.add_symbol(symbol, tick, lower, upper)) {
            out << "ERR invalid band or orders still resting\n";
            return;
        }
        out << "OK\n";
    } else if (cmd == "PING") {
        out << "PONG\n";
    } else {
        out << "ERR unknown command\n";
    }
}

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    ob::Engine engine;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        handle(engine, line, std::cout);
        std::cout << "END\n" << std::flush;
    }
    return 0;
}
