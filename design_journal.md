# Design Journal

Yes, I'm journaling my thought processa as I create the project


## Data design

4 domains: Market Data, Port data, analytics, Reference Data


```
Market Data
------------
Assets
Prices
Dividends
Splits

Portfolio Data
--------------
Portfolios
Holdings
Transactions

Analytics
----------
OptimizationRuns
OptimizationResults
RiskMetrics

Reference Data
--------------
AssetTypes
Sectors
Countries
Currencies
```


eventual growth into:
```
Assets
│
├── Prices
├── Dividends
├── Splits
├── Financial Statements
├── News
├── Earnings

Portfolio
│
├── Transactions
├── Holdings
├── Cash
├── Performance
├── Benchmarks

Optimization
│
├── Efficient Frontier
├── Risk Parity
├── HRP
├── Black-Litterman

Analytics
│
├── VaR
├── CVaR
├── Monte Carlo
├── Drawdown
├── Beta
├── Alpha
├── Tracking Error

Machine Learning
│
├── Forecasts
├── Features
├── Models
└── Predictions
```