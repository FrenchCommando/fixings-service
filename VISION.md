https://github.com/FrenchCommando/spot-fixings is a public repo, i cloned it in `~/`
it uses `thetadata` through a `jar`
now that it has a python package, we can skip the jar and run code directly
credentials: settled. thetadata always requires an account (no anonymous access), but there is a free EOD tier for us stocks (1-day delayed, history from june 2023). i'll use my own credentials anyway - i have a VALUE-level subscription for options. so credentials are a non-issue for me.
note: since the data is account-gated/licensed, it cannot be redistributed publicly -> public github-pages with real fixings is off the table (personal/self-hosted use only). the new python lib connects directly over grpc with no jar/jvm, so the "skip the jar" plan is confirmed.

this is also an excuse to proof-read the python code from the new package
using yfinance as a backup still makes sense, it's good to be resilient.

feel free to improve the design, expecially the UI

curious if this can live in github-pages

I might want to host this on my raspberrypi - so docker and nginx setup can be an option
