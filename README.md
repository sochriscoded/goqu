# goqu

a local trading journal, portfolio analyis, research and discovery, and planning application. No need to use a specific brokerage or service. You can hook up a supported api for data access and get quotes, charts, and information, all in one place.



- DB lives at ~/.config/goqu/goqu.db (Linux) OR AppData/Roaming/goqu/goqu.db (Windows)
    - Creates account and app_settings tables on first run
    - API key stored in app_settings table keyed as
      alpha_vantage_api_key
    - Other options will be available as time goes on. For now I'm just sticking to Alphavantage.