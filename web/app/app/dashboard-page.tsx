// DEPRECATED - DELETE THIS FILE
// The real dashboard is at /app/app/page.tsx

// Empty export to prevent build errors
const _unused = null;
export { _unused };
  const [account, setAccount] = useState<RxAccount | null>(null);
  const [trades, setTrades] = useState<TradeIdea[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [acc, trd] = await Promise.all([fetchRxAccount(), fetchTrades()]);
      setAccount(acc);
      setTrades(trd);
      setLoading(false);
    };
    load();
    const i = setInterval(load, 10_000);
    return () => clearInterval(i);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <p className="text-muted-foreground animate-pulse">Loading your dashboard…</p>
      </div>
    );
  }

  const pendingApproval = trades.filter((t) => t.status === "Ready for Approval");
  const approved = trades.filter((t) => t.status === "Approved");
  const executed = trades.filter((t) => t.status === "Sent" || t.status === "Filled");
  const rejected = trades.filter((t) => t.status === "Rejected");

  const totalBalance =
    account?.balances.reduce((sum, b) => {
      // Simple heuristic: show EUR as-is, assume BTC/ETH etc. are in small fractions
      if (b.currency === "EUR" || b.currency === "USD") return sum + b.balance;
      return sum;
    }, 0) ?? 0;

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground mb-1">
          Good afternoon, Declan.
        </h1>
        <p className="text-muted-foreground">Here's what Aurum OS is tracking for you.</p>
      </div>

      {/* Account Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Total Balance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-foreground">
              €{totalBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Revolut X · Live</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Pending Approvals
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{pendingApproval.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {pendingApproval.length === 1 ? "Trade awaiting your call" : "Trades awaiting review"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Active Positions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-emerald-500">{executed.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Currently in the market</p>
          </CardContent>
        </Card>
      </div>

      {/* Asset Breakdown */}
      {account && account.balances.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-foreground">Your Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {account.balances
                .filter((b) => b.balance > 0)
                .sort((a, b) => b.balance - a.balance)
                .map((bal) => (
                  <div key={bal.currency} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
                        {bal.currency.substring(0, 2)}
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">{bal.currency}</p>
                        <p className="text-xs text-muted-foreground">
                          {bal.available > 0 ? `${bal.available.toFixed(8)} available` : "Reserved"}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-foreground font-semibold">{bal.balance.toFixed(8)}</p>
                      {bal.reserved > 0 && (
                        <p className="text-xs text-muted-foreground">{bal.reserved.toFixed(8)} reserved</p>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Recommendations */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-lg font-semibold text-foreground">
            Aurum Recommendations · Guardian AI
          </CardTitle>
          <Link href="/app/approvals">
            <Button variant="outline" size="sm" className="gap-2">
              Review All <ArrowRight className="w-3 h-3" />
            </Button>
          </Link>
        </CardHeader>
        <CardContent>
          {pendingApproval.length === 0 ? (
            <div className="py-8 text-center">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">No pending recommendations. All clear.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pendingApproval.slice(0, 3).map((trade) => {
                const isLong = trade.direction === "Long";
                return (
                  <div
                    key={trade.id}
                    className="p-4 rounded-lg border border-border bg-card hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Badge variant={isLong ? "default" : "destructive"} className="font-mono text-[10px]">
                          {trade.direction}
                        </Badge>
                        <span className="font-bold text-foreground">{trade.symbol}</span>
                      </div>
                      <Badge variant="outline" className="text-primary border-primary/20 bg-primary/10">
                        {trade.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{trade.thesis}</p>
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-4 text-muted-foreground">
                        <span>
                          Entry: <span className="font-mono text-foreground">{trade.entry_price}</span>
                        </span>
                        <span>
                          SL: <span className="font-mono text-foreground">{trade.stop_loss}</span>
                        </span>
                        <span>
                          TP: <span className="font-mono text-foreground">{trade.take_profit}</span>
                        </span>
                      </div>
                      <Link href="/app/approvals">
                        <Button variant="ghost" size="sm" className="h-7 text-xs gap-1">
                          Review <ArrowRight className="w-3 h-3" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent Activity Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Clock className="w-4 h-4" /> Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">{approved.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Awaiting execution</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4" /> Executed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-500">{executed.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Live positions</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <AlertCircle className="w-4 h-4" /> Rejected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">{rejected.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Did not meet criteria</p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <Link href="/app/approvals" className="flex-1">
          <Button className="w-full gap-2" size="lg">
            <AlertCircle className="w-4 h-4" />
            Review Pending Trades
          </Button>
        </Link>
        <Link href="/app/planner" className="flex-1">
          <Button variant="outline" className="w-full gap-2" size="lg">
            Plan New Trade
          </Button>
        </Link>
      </div>
    </div>
  );
}
