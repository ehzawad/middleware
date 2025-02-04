### Rasa server paradigm

NLU only server

NLG server

Rasa custom server

Rasa middleware service

Rasa Client server

There are many ways you can run stuff and manipulate dialouge flow in Rasa (Rasa Open Source version)

#### How to run stuff:

```bash
rasa run -m models --enable-api --cors "*" --endpoints endpoints.yml --port 5005
python3 -m rasa_sdk --actions actions --port 6060
python3 middleware.py
python3 all_simple.py
highlight_log_keyword.sh "followup_action" "next_action" "latest_action_name" < /path/to/middleware.log
```
# middleware_proxy_rasa
