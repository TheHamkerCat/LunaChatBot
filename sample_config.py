HEROKU = True # Make it False if you're not deploying on heroku.

if HEROKU:
    from os import environ

    bot_token = environ["5646977959:AAHUgIS4cxav6AQs5i5hcdlBcUD4RwF2hU0"]
    ARQ_API_KEY = environ["XQBIJV-QGSIOH-ROVLWH-PWARNF-ARQ"]
    LANGUAGE = environ["LANGUAGE"]

# NOTE Fill this if you are not deploying on heroku.
if not HEROKU:

    bot_token = "5646977959:AAHUgIS4cxav6AQs5i5hcdlBcUD4RwF2hU0"
    ARQ_API_KEY = "XQBIJV-QGSIOH-ROVLWH-PWARNF-ARQ"
# List of supported languages >>
# https://py-googletrans.readthedocs.io/en/latest/#googletrans-languages
    LANGUAGE = "en"

# Leave it as it is
ARQ_API_BASE_URL = "https://arq.hamker.in"
