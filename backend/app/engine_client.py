"""Talks to the C++ matching engine process over its stdin/stdout text protocol."""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class EngineError(RuntimeError):
    pass


@dataclass
class EngineTrade:
    buy_id: int
    sell_id: int
    price: int
    qty: int


@dataclass
class EngineResult:
    reject: str | None = None
    trades: list[EngineTrade] = field(default_factory=list)
    filled: int = 0
    resting: int = 0
    cancelled: int = 0


Level = tuple[int, int, int]  # price, quantity, number of orders


class EngineClient:
    """Not thread safe: callers must send one command at a time (the exchange lock does this)."""

    def __init__(self, binary: Path):
        if not binary.exists():
            raise EngineError(f"Matching engine not built: {binary}. Run: cmake -S engine -B engine/build && cmake --build engine/build")
        self._proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def _call(self, line: str) -> list[list[str]]:
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            replies = []
            while True:
                reply = self._proc.stdout.readline()
                if not reply:
                    raise EngineError("matching engine stopped")
                reply = reply.strip()
                if reply == "END":
                    return replies
                replies.append(reply.split())
        except (BrokenPipeError, ValueError) as err:
            raise EngineError("matching engine is not running") from err

    def ping(self) -> bool:
        return self._call("PING") == [["PONG"]]

    def add_symbol(self, symbol: str, tick: int, lower_band: int, upper_band: int) -> None:
        reply = self._call(f"SYM {symbol} {tick} {lower_band} {upper_band}")
        if reply != [["OK"]]:
            raise EngineError(f"engine refused symbol {symbol}: {reply}")

    def new_order(self, order_id: int, symbol: str, side: str, order_type: str, price: int, qty: int) -> EngineResult:
        """side is 'BUY' or 'SELL'; order_type is 'LIMIT' or 'MARKET'."""
        result = EngineResult()
        for parts in self._call(f"NEW {order_id} {symbol} {side[0]} {order_type[0]} {price} {qty}"):
            kind = parts[0]
            if kind == "TRD":
                result.trades.append(EngineTrade(int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])))
            elif kind == "FIN":
                result.filled, result.resting, result.cancelled = int(parts[2]), int(parts[3]), int(parts[4])
            elif kind == "REJ":
                result.reject = parts[2]
            elif kind == "ERR":
                raise EngineError(" ".join(parts))
        return result

    def cancel(self, order_id: int) -> int:
        """Returns the quantity removed from the book, or 0 if the order was not resting."""
        for parts in self._call(f"CXL {order_id}"):
            if parts[0] == "CXD":
                return int(parts[2])
        return 0

    def depth(self, symbol: str, levels: int) -> tuple[list[Level], list[Level]]:
        bids: list[Level] = []
        asks: list[Level] = []
        for parts in self._call(f"DEP {symbol} {levels}"):
            if parts[0] == "BID":
                bids.append((int(parts[1]), int(parts[2]), int(parts[3])))
            elif parts[0] == "ASK":
                asks.append((int(parts[1]), int(parts[2]), int(parts[3])))
            elif parts[0] == "ERR":
                raise EngineError(" ".join(parts))
        return bids, asks

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
