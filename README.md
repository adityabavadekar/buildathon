# FORTX - Flow Orchestration & Revenue Trust eXecution

FORTX watches for revenue that's about to be lost - a failed payment, an
abandoned checkout, a subscription that stopped renewing, an overdue
invoice - figures out why, and takes one bounded action to recover it: a
retry, a payment link, a reminder, or a handoff to a human. Every batch is
measured against a 10% holdout group that never gets contacted, so the
recovery numbers are real, not just claimed.

Built for the Razorpay AI Buildathon, Track 3 (AI Revenue Recovery), on top
of [Razorpay's API](https://razorpay.com/docs/api/) and webhooks.

![Dashboard screenshot placeholder](docs/screenshot-dashboard.png)


## How it works

A failed payment, an abandoned checkout, a halted subscription mandate, and
an overdue invoice are all the same problem underneath: money that almost
came in and then didn't. FORTX picks up the failure event, has an LLM (or a
plain rule-based fallback if no AI provider is set up) work out what went
wrong and choose one bounded response, then runs that response through a
policy check with hard limits and cooldowns before anything happens. Every
decision is logged before it's acted on. One in ten cases is held back on
purpose and never contacted, so recovery can be compared against doing
nothing.


## What it does

- Catches failures across payments, checkout, subscriptions, and invoices
- Uses an LLM to diagnose the failure and pick a strategy, with a rule-based
  fallback when no AI provider is configured
- Takes bounded action: smart retries, payment links, Smart Collect virtual
  accounts, WhatsApp/SMS/voice messages, or chasing a B2B invoice
- Places outbound Hinglish voice calls, using Sarvam AI for the speech
- Enforces limits before anything runs: contact caps, cooldowns, discount
  caps, opt-outs, and a value threshold requiring human approval
- Handles the full set of Razorpay webhooks: payments, refunds, disputes,
  subscriptions, payment links, invoices, and Smart Collect
- Keeps a plain-language record of every decision made and why
- Holds back 10% of cases from contact, as a real comparison group
- Includes a benchmark tool that replays a fixed dataset and reports lift
  over doing nothing
- Lets a merchant edit the rules, choose an AI provider, and connect
  Razorpay via OAuth or an API key pair


## The dashboard

- **Overview / Analytics** - at-risk revenue, recovered revenue, and lift
  over the holdout group
- **Transactions / Awaiting Approval** - the case list and human sign-off queue
- **Audit Log** - plain-language history of every decision
- **AI Agent Telemetry** - model, tokens, cost, and latency in real time
- **Data Pipeline / System Status** (dev) - queue depth and worker health
- **Merchant Policies / Integrations** - limits and Razorpay connection


## What you'll need

- Python 3.13, as pinned in `backend/.python-version`
- uv
- Node 22
- pnpm 11, through corepack
- Docker, for the PostgreSQL database
- An AI provider key is optional; without one it uses the rule-based
  fallback. Supported providers: OpenRouter, Anthropic, OpenAI, and Groq


## Getting it running

1. Make sure you have everything listed above installed.

2. Clone the repo and enter it:

```bash
git clone https://github.com/adityabavadekar/buildathon.git
cd buildathon
```

3. Copy the example environment file:

```bash
cp backend/.env.example backend/.env
```

4. Install everything and start the database:

```bash
make setup
```

5. Start the backend and the frontend:

```bash
make dev
```

The backend runs on port 8000, the frontend on port 5173.

6. In another terminal, start the background worker. Without it, jobs just
   sit queued:

```bash
make worker
```

To see everything else you can run:

```bash
make help
```


## Configuration

`backend/.env.example` already has the settings you'd want, with an
explanation next to each one.


## Setting up integrations

These are optional; without them the matching feature just simulates.

**Razorpay** - get a key pair from the
[Razorpay dashboard](https://dashboard.razorpay.com/), or register a
[Technology Partner OAuth](https://razorpay.com/docs/partners/technology-partners/onboard-businesses/integrate-oauth/)
app, and fill in the matching `RAZORPAY_*` variables.

**Sarvam AI + Twilio** - for outbound Hinglish voice calls, get a key from
[Sarvam AI](https://www.sarvam.ai/) and a [Twilio](https://www.twilio.com/)
account, and fill in `SARVAM_API_KEY` and the `TWILIO_*` variables.

**WhatsApp** - set up a
[Meta WhatsApp Business Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/)
app and fill in the `WHATSAPP_*` variables.


## License

Apache License 2.0 - see [LICENSE](LICENSE).
