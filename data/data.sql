CREATE TABLE `portfolio`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` CHAR(255) NOT NULL,
    `created_at` DATETIME NOT NULL,
    `description` BIGINT NOT NULL,
    `updated_at` BIGINT NOT NULL,
    `benchmark_asset_id` BIGINT NOT NULL
);
CREATE TABLE `holdings`(
    `portfolio_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `asset_id` CHAR(255) NOT NULL,
    `shares` DOUBLE NOT NULL,
    `cost_basis` DOUBLE NOT NULL,
    `purchase_price` DOUBLE NOT NULL,
    `created_at` DATETIME NOT NULL
);
ALTER TABLE
    `holdings` ADD UNIQUE `holdings_asset_id_unique`(`asset_id`);
CREATE TABLE `transactions`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `portfolio_id` BIGINT NOT NULL,
    `asset_id` BIGINT NOT NULL,
    `date` DATE NOT NULL,
    `transaction_type` BIGINT NOT NULL,
    `shares` BIGINT NOT NULL,
    `price` BIGINT NOT NULL,
    `fees` BIGINT NOT NULL,
    `notes` BIGINT NOT NULL
);
CREATE TABLE `assets`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `symbol` VARCHAR(255) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `asset_type_id` BIGINT NOT NULL,
    `exchange` VARCHAR(255) NOT NULL,
    `currency` VARCHAR(255) NOT NULL,
    `sector` VARCHAR(255) NOT NULL,
    `industry` VARCHAR(255) NOT NULL,
    `country` VARCHAR(255) NOT NULL,
    `is_active` BOOLEAN NOT NULL,
    `created_at` DATETIME NOT NULL
);
ALTER TABLE
    `assets` ADD UNIQUE `assets_symbol_unique`(`symbol`);
CREATE TABLE `asset_type`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL
);
CREATE TABLE `daily_price`(
    `asset_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `date` DATE NOT NULL,
    `open` FLOAT(53) NOT NULL,
    `high` FLOAT(53) NOT NULL,
    `low` FLOAT(53) NOT NULL,
    `adjusted_close` FLOAT(53) NOT NULL,
    `volume` BIGINT NOT NULL
);
CREATE TABLE `optimization_runs`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `portfolio_id` BIGINT NOT NULL,
    `algorithm` TEXT NOT NULL,
    `expected_return` FLOAT(53) NOT NULL,
    `expected_volatility` FLOAT(53) NOT NULL,
    `sharpe_ratio` FLOAT(53) NOT NULL,
    `created_at` DATETIME NOT NULL
);
CREATE TABLE `optimization_allocations`(
    `optimization_run_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `asset_id` BIGINT NOT NULL,
    `recommended_weight` FLOAT(53) NOT NULL
);
CREATE TABLE `risk_metrics`(
    `portfolio_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `date` DATE NOT NULL,
    `volatility` BIGINT NOT NULL,
    `sharpe` BIGINT NOT NULL,
    `sortino` BIGINT NOT NULL,
    `max_drawdown` BIGINT NOT NULL,
    `var95` BIGINT NOT NULL,
    `cvar95` BIGINT NOT NULL
);
ALTER TABLE
    `optimization_allocations` ADD CONSTRAINT `optimization_allocations_asset_id_foreign` FOREIGN KEY(`asset_id`) REFERENCES `assets`(`id`);
ALTER TABLE
    `transactions` ADD CONSTRAINT `transactions_portfolio_id_foreign` FOREIGN KEY(`portfolio_id`) REFERENCES `portfolio`(`id`);
ALTER TABLE
    `assets` ADD CONSTRAINT `assets_asset_type_id_foreign` FOREIGN KEY(`asset_type_id`) REFERENCES `asset_type`(`id`);
ALTER TABLE
    `holdings` ADD CONSTRAINT `holdings_portfolio_id_foreign` FOREIGN KEY(`portfolio_id`) REFERENCES `portfolio`(`id`);
ALTER TABLE
    `risk_metrics` ADD CONSTRAINT `risk_metrics_portfolio_id_foreign` FOREIGN KEY(`portfolio_id`) REFERENCES `portfolio`(`id`);
ALTER TABLE
    `daily_price` ADD CONSTRAINT `daily_price_asset_id_foreign` FOREIGN KEY(`asset_id`) REFERENCES `assets`(`id`);
ALTER TABLE
    `optimization_runs` ADD CONSTRAINT `optimization_runs_portfolio_id_foreign` FOREIGN KEY(`portfolio_id`) REFERENCES `portfolio`(`id`);
ALTER TABLE
    `optimization_allocations` ADD CONSTRAINT `optimization_allocations_optimization_run_id_foreign` FOREIGN KEY(`optimization_run_id`) REFERENCES `optimization_runs`(`id`);