"""
MEMORY AGENT — The Learning Brain
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is what makes the agent superhuman.

It remembers:
- Every trade (success & failure) with full context
- Every news event and what price did after
- Every signal that was RIGHT or WRONG
- Pattern: "When RSI < 40 + positive news → avg return was +4.2%"
- Pattern: "When global sentiment negative → 73% of BUY signals failed"

It uses these memories to:
- Adjust signal score thresholds dynamically
- Boost or reduce confidence based on past patterns
- Write its own updated rules every week
- Never repeat the same mistake twice

The more it trades, the smarter it gets.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

log = logging.getLogger("MemoryAgent")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

class MemoryAgent:
    def __init__(self):
        self.memory = self._load()

    def _load(self) -> dict:
        f = DATA_DIR / "agent_memory.json"
        if f.exists():
            return json.loads(f.read_text())
        return {
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),

            # Core memory stores
            "trade_memories": [],          # every trade with full context + outcome
            "news_memories": [],           # news events + what happened to price after
            "pattern_library": {},         # learned patterns with success rates
            "mistake_log": [],             # specific mistakes + lessons learned
            "rule_adjustments": [],        # self-written rule changes over time

            # Learned thresholds (start at defaults, agent adjusts these)
            "learned_thresholds": {
                "buy_score_min": 3.0,      # agent may raise this if too many bad buys
                "sell_score_max": -3.0,    # agent may lower this for faster exits
                "stop_loss_pct": 5.0,      # agent may tighten/loosen based on volatility
                "min_rsi_for_buy": 0,      # agent learns: "never buy RSI > X"
                "max_rsi_for_buy": 100,
                "news_weight": 1.0,        # agent adjusts how much to trust news
                "global_weight": 1.0,      # agent adjusts global macro weight
            },

            # Statistics
            "stats": {
                "total_trades_learned_from": 0,
                "total_news_events_processed": 0,
                "rules_written": 0,
                "accuracy_history": [],    # weekly accuracy %
                "best_pattern": None,
                "worst_pattern": None,
            }
        }

    def _save(self):
        self.memory["last_updated"] = datetime.now().isoformat()
        (DATA_DIR / "agent_memory.json").write_text(json.dumps(self.memory, indent=2))

    # ── LEARNING FROM TRADES ────────────────────────────────────────────────

    def record_trade_opened(self, symbol: str, signal: dict, market_context: dict):
        """Called when BUY is executed. Records full context for future learning."""
        memory = {
            "id": f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "symbol": symbol,
            "type": "BUY",
            "date_opened": datetime.now().isoformat(),
            "date_closed": None,
            "entry_price": signal.get("latest_price"),
            "exit_price": None,
            "pnl": None,
            "pnl_pct": None,
            "outcome": None,  # WIN / LOSS / BREAK_EVEN — filled on close

            # Context at time of buy (for pattern learning)
            "context": {
                "score": signal.get("score"),
                "rsi": signal.get("rsi"),
                "sma20": signal.get("sma20"),
                "sma50": signal.get("sma50"),
                "news_sentiment": signal.get("news_sentiment"),
                "global_sentiment": signal.get("global_sentiment"),
                "reasons": signal.get("reasons", []),
                "market_trend": market_context.get("nifty_trend", "UNKNOWN"),
                "vix": market_context.get("vix", None),
            }
        }
        self.memory["trade_memories"].append(memory)
        self._save()
        log.info(f"[Memory] Recorded BUY context for {symbol}")
        return memory["id"]

    def record_trade_closed(self, symbol: str, exit_price: float, pnl: float, reason: str):
        """Called when position closed. Completes memory + triggers learning."""
        # Find the open trade
        for trade in reversed(self.memory["trade_memories"]):
            if trade["symbol"] == symbol and trade["date_closed"] is None:
                trade["date_closed"] = datetime.now().isoformat()
                trade["exit_price"] = exit_price
                trade["pnl"] = round(pnl, 2)
                entry = trade["entry_price"] or exit_price
                trade["pnl_pct"] = round((exit_price - entry) / entry * 100, 2) if entry else 0
                trade["close_reason"] = reason

                if pnl > 0:
                    trade["outcome"] = "WIN"
                elif pnl < 0:
                    trade["outcome"] = "LOSS"
                else:
                    trade["outcome"] = "BREAK_EVEN"

                self.memory["stats"]["total_trades_learned_from"] += 1
                self._save()

                # Trigger learning from this trade
                lesson = self._learn_from_trade(trade)
                log.info(f"[Memory] Trade closed: {symbol} | {trade['outcome']} | ₹{pnl} | Lesson: {lesson}")
                return lesson
        return None

    def _learn_from_trade(self, trade: dict) -> str:
        """Analyze a closed trade and extract a lesson."""
        ctx = trade["context"]
        outcome = trade["outcome"]
        pnl_pct = trade["pnl_pct"]
        lesson = ""

        # ── Pattern: RSI range ──────────────────────────────
        if ctx.get("rsi"):
            rsi = ctx["rsi"]
            rsi_bucket = f"rsi_{int(rsi//10)*10}_{int(rsi//10)*10+10}"
            self._update_pattern(rsi_bucket, outcome, pnl_pct,
                                 f"RSI in {int(rsi//10)*10}-{int(rsi//10)*10+10} range")

        # ── Pattern: News + Score combo ─────────────────────
        news = ctx.get("news_sentiment", "NEUTRAL")
        score = ctx.get("score", 0)
        combo_key = f"news_{news}_score_{int(score)}"
        self._update_pattern(combo_key, outcome, pnl_pct,
                             f"News={news} + Score≈{int(score)}")

        # ── Pattern: Global sentiment ────────────────────────
        global_sent = ctx.get("global_sentiment", "NEUTRAL")
        global_key = f"global_{global_sent}"
        self._update_pattern(global_key, outcome, pnl_pct,
                             f"Global sentiment was {global_sent}")

        # ── Self-write rules based on patterns ──────────────
        lesson = self._write_rules_from_patterns()

        # ── Log mistakes ─────────────────────────────────────
        if outcome == "LOSS" and abs(pnl_pct) > 3:
            mistake = {
                "date": datetime.now().isoformat(),
                "symbol": trade["symbol"],
                "loss_pct": pnl_pct,
                "context": ctx,
                "lesson": f"Avoid buying when: RSI={ctx.get('rsi')}, news={news}, score={score}",
                "rule_added": lesson,
            }
            self.memory["mistake_log"].append(mistake)
            log.warning(f"[Memory] Mistake logged: {mistake['lesson']}")

        self._save()
        return lesson

    def _update_pattern(self, key: str, outcome: str, pnl_pct: float, description: str):
        """Update a pattern's statistics."""
        lib = self.memory["pattern_library"]
        if key not in lib:
            lib[key] = {
                "description": description,
                "trades": 0, "wins": 0, "losses": 0,
                "total_pnl_pct": 0, "avg_pnl_pct": 0,
                "win_rate": 0, "confidence": "LOW"
            }
        p = lib[key]
        p["trades"] += 1
        p["total_pnl_pct"] = round(p["total_pnl_pct"] + pnl_pct, 2)
        p["avg_pnl_pct"] = round(p["total_pnl_pct"] / p["trades"], 2)
        if outcome == "WIN":
            p["wins"] += 1
        elif outcome == "LOSS":
            p["losses"] += 1
        p["win_rate"] = round(p["wins"] / p["trades"] * 100, 1)
        # Confidence grows with sample size
        if p["trades"] >= 20:
            p["confidence"] = "HIGH"
        elif p["trades"] >= 10:
            p["confidence"] = "MEDIUM"
        else:
            p["confidence"] = "LOW"

        # Update best/worst patterns
        if p["trades"] >= 5:
            best = self.memory["stats"]["best_pattern"]
            if not best or p["avg_pnl_pct"] > lib.get(best, {}).get("avg_pnl_pct", 0):
                self.memory["stats"]["best_pattern"] = key
            worst = self.memory["stats"]["worst_pattern"]
            if not worst or p["avg_pnl_pct"] < lib.get(worst, {}).get("avg_pnl_pct", 0):
                self.memory["stats"]["worst_pattern"] = key

    def _write_rules_from_patterns(self) -> str:
        """
        Agent writes its own trading rules based on what it has learned.
        These override the default thresholds dynamically.
        """
        lib = self.memory["pattern_library"]
        thresholds = self.memory["learned_thresholds"]
        rules_written = []

        for key, pattern in lib.items():
            if pattern["trades"] < 5 or pattern["confidence"] == "LOW":
                continue  # not enough data yet

            # Rule: If global negative always causes losses → increase sell threshold
            if "global_NEGATIVE" in key and pattern["win_rate"] < 30:
                if thresholds["global_weight"] > 0.5:
                    thresholds["global_weight"] = round(thresholds["global_weight"] - 0.1, 2)
                    rules_written.append(
                        f"Reduced global_weight to {thresholds['global_weight']} "
                        f"(global NEGATIVE has {pattern['win_rate']}% win rate)"
                    )

            # Rule: RSI pattern — if high RSI buys keep losing, raise max RSI for buy
            if "rsi_70_80" in key and pattern["win_rate"] < 35:
                thresholds["max_rsi_for_buy"] = 68
                rules_written.append("Learned: Never buy when RSI > 68 (high RSI buys failing)")

            if "rsi_30_40" in key and pattern["win_rate"] > 65:
                thresholds["min_rsi_for_buy"] = 30
                rules_written.append("Confirmed: RSI 30-40 is a reliable buy zone")

            # Rule: If many losses → tighten buy threshold
            if pattern["win_rate"] < 30 and pattern["trades"] >= 10:
                if thresholds["buy_score_min"] < 5.0:
                    thresholds["buy_score_min"] = round(thresholds["buy_score_min"] + 0.5, 1)
                    rules_written.append(
                        f"Raised buy threshold to {thresholds['buy_score_min']} (too many losses)"
                    )

            # Rule: If news positive + high score is winning consistently → trust it more
            if "news_POSITIVE" in key and pattern["win_rate"] > 70 and pattern["trades"] >= 8:
                if thresholds["news_weight"] < 1.5:
                    thresholds["news_weight"] = round(thresholds["news_weight"] + 0.1, 2)
                    rules_written.append(
                        f"Increased news_weight to {thresholds['news_weight']} "
                        f"(positive news is highly reliable)"
                    )

        if rules_written:
            for rule in rules_written:
                self.memory["rule_adjustments"].append({
                    "date": datetime.now().isoformat(),
                    "rule": rule
                })
            self.memory["stats"]["rules_written"] += len(rules_written)
            log.info(f"[Memory] Agent wrote {len(rules_written)} new rules")
            return " | ".join(rules_written)

        return "No rule changes needed yet"

    # ── LEARNING FROM NEWS ──────────────────────────────────────────────────

    def record_news_event(self, symbol: str, headline: str, sentiment: str, price_at_time: float):
        """Record a news event. Price outcome checked later."""
        event = {
            "id": f"news_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "symbol": symbol,
            "headline": headline[:150],
            "sentiment": sentiment,
            "price_at_time": price_at_time,
            "price_24h_later": None,      # filled by follow_up_news_outcomes()
            "price_change_pct": None,
            "date": datetime.now().isoformat(),
            "outcome_checked": False,
        }
        self.memory["news_memories"].append(event)
        self.memory["stats"]["total_news_events_processed"] += 1
        # Keep last 500 news memories only
        if len(self.memory["news_memories"]) > 500:
            self.memory["news_memories"] = self.memory["news_memories"][-500:]
        self._save()

    def follow_up_news_outcomes(self, current_prices: dict):
        """
        Called every cycle. Checks if news from 24h ago was accurate.
        Teaches agent which news sources/types to trust.
        """
        cutoff = datetime.now() - timedelta(hours=24)
        for event in self.memory["news_memories"]:
            if event["outcome_checked"]:
                continue
            event_date = datetime.fromisoformat(event["date"])
            if event_date > cutoff:
                continue  # less than 24h ago, too early

            symbol = event["symbol"]
            if symbol in current_prices:
                current = current_prices[symbol]
                entry = event["price_at_time"]
                if entry and entry > 0:
                    change = (current - entry) / entry * 100
                    event["price_24h_later"] = current
                    event["price_change_pct"] = round(change, 2)
                    event["outcome_checked"] = True

                    # Did the news sentiment predict correctly?
                    correct = (
                        (event["sentiment"] == "POSITIVE" and change > 0) or
                        (event["sentiment"] == "NEGATIVE" and change < 0)
                    )
                    event["sentiment_was_correct"] = correct
                    key = f"news_accuracy_{event['sentiment']}"
                    self._update_pattern(
                        key, "WIN" if correct else "LOSS", change,
                        f"News sentiment {event['sentiment']} prediction accuracy"
                    )

        self._save()

    # ── MEMORY-ADJUSTED SIGNAL ──────────────────────────────────────────────

    def adjust_signal(self, signal: dict) -> dict:
        """
        Takes a raw signal and adjusts it based on learned memory.
        This is where memory makes the agent smarter over time.
        """
        thresholds = self.memory["learned_thresholds"]
        lib = self.memory["pattern_library"]
        adjusted = signal.copy()
        memory_notes = []

        rsi = signal.get("rsi", 50)
        score = signal.get("score", 0)
        news = signal.get("news_sentiment", "NEUTRAL")
        global_sent = signal.get("global_sentiment", "NEUTRAL")

        # Apply learned RSI bounds
        if rsi and rsi > thresholds.get("max_rsi_for_buy", 100):
            adjusted["action"] = "HOLD"
            adjusted["score"] = min(score, 2.5)
            memory_notes.append(f"Memory override: RSI {rsi} > learned max {thresholds['max_rsi_for_buy']}")

        # Apply global weight adjustment
        if global_sent == "NEGATIVE":
            gw = thresholds.get("global_weight", 1.0)
            if gw < 0.8:
                adjusted["score"] = round(score * 0.8, 1)
                memory_notes.append(f"Memory: Global negative has been unreliable (weight={gw}), reducing score")

        # Check pattern library for this specific context
        rsi_key = f"rsi_{int(rsi//10)*10}_{int(rsi//10)*10+10}" if rsi else None
        if rsi_key and rsi_key in lib:
            pattern = lib[rsi_key]
            if pattern["confidence"] in ["MEDIUM", "HIGH"]:
                if pattern["win_rate"] > 70:
                    adjusted["score"] = round(score + 0.5, 1)
                    memory_notes.append(f"Memory boost: This RSI range has {pattern['win_rate']}% win rate")
                elif pattern["win_rate"] < 35:
                    adjusted["score"] = round(score - 1.0, 1)
                    memory_notes.append(f"Memory penalty: This RSI range has only {pattern['win_rate']}% win rate")

        # News accuracy pattern
        news_key = f"news_accuracy_{news}"
        if news_key in lib:
            pattern = lib[news_key]
            if pattern["confidence"] != "LOW":
                nw = thresholds.get("news_weight", 1.0)
                if pattern["win_rate"] > 65 and nw > 1.0:
                    memory_notes.append(f"Memory: {news} news has been {pattern['win_rate']}% accurate")
                elif pattern["win_rate"] < 45:
                    adjusted["score"] = round(score * 0.9, 1)
                    memory_notes.append(f"Memory: {news} news accuracy only {pattern['win_rate']}%")

        adjusted["memory_notes"] = memory_notes
        adjusted["memory_adjusted"] = len(memory_notes) > 0
        adjusted["learned_buy_threshold"] = thresholds["buy_score_min"]

        if memory_notes:
            log.info(f"[Memory] Signal adjusted for {signal.get('symbol')}: {' | '.join(memory_notes)}")

        return adjusted

    # ── REPORTING ───────────────────────────────────────────────────────────

    def get_insights(self) -> dict:
        """Return a human-readable summary of what the agent has learned."""
        lib = self.memory["pattern_library"]
        thresholds = self.memory["learned_thresholds"]

        # Top patterns by confidence and win rate
        reliable = sorted(
            [(k, v) for k, v in lib.items() if v["trades"] >= 5],
            key=lambda x: x[1]["win_rate"], reverse=True
        )[:5]

        recent_rules = self.memory["rule_adjustments"][-5:]
        recent_mistakes = self.memory["mistake_log"][-3:]

        total_trades = self.memory["stats"]["total_trades_learned_from"]
        wins = sum(1 for t in self.memory["trade_memories"] if t.get("outcome") == "WIN")
        losses = sum(1 for t in self.memory["trade_memories"] if t.get("outcome") == "LOSS")
        win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0

        return {
            "summary": {
                "total_trades_learned": total_trades,
                "overall_win_rate": f"{win_rate}%",
                "patterns_discovered": len(lib),
                "rules_self_written": self.memory["stats"]["rules_written"],
                "news_events_analyzed": self.memory["stats"]["total_news_events_processed"],
            },
            "current_learned_thresholds": thresholds,
            "top_reliable_patterns": [
                {"pattern": v["description"], "win_rate": f"{v['win_rate']}%",
                 "trades": v["trades"], "avg_return": f"{v['avg_pnl_pct']}%"}
                for k, v in reliable
            ],
            "recent_rules_written": [r["rule"] for r in recent_rules],
            "recent_mistakes_learned": [m["lesson"] for m in recent_mistakes],
            "last_updated": self.memory["last_updated"],
        }

    def get_telegram_weekly_report(self) -> str:
        insights = self.get_insights()
        s = insights["summary"]
        patterns = insights["top_reliable_patterns"][:3]
        rules = insights["recent_rules_written"][:3]

        pattern_lines = "\n".join([f"  • {p['pattern']}: {p['win_rate']} win rate" for p in patterns])
        rule_lines = "\n".join([f"  • {r}" for r in rules]) if rules else "  • Still learning..."

        return (
            f"🧠 <b>AGENT WEEKLY LEARNING REPORT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Trades Analyzed: {s['total_trades_learned']}\n"
            f"🎯 Overall Win Rate: {s['overall_win_rate']}\n"
            f"🔍 Patterns Found: {s['patterns_discovered']}\n"
            f"📝 Rules Self-Written: {s['rules_self_written']}\n"
            f"📰 News Events Learned: {s['news_events_analyzed']}\n\n"
            f"<b>Top Reliable Patterns:</b>\n{pattern_lines}\n\n"
            f"<b>Rules Agent Wrote Itself:</b>\n{rule_lines}"
        )
