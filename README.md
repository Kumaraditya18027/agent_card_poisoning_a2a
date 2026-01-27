
## Setup

1. **Clone & navigate**

    ```bash
    git clone https://github.com/theailanguage/a2a_samples.git
    cd a2a_samples/version_3_multi_agent
    ```

2. **Create & activate a venv**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install dependencies**

    ```bash
    pip install -r requirements.txt
    ```

4. **Set your API key**

    Create `.env` at the project root:
    ```bash
    echo "GOOGLE_API_KEY=your_api_key_here" > .env
    ```

---

## Demo Walkthrough

**Start the HotelBooking agent**
```bash
python3 -m agents.hotel_booking_agent \
  --host localhost --port 10003
```


**Start the Orchestrator (Host) Agent**
```bash
python3 -m agents.host_agent.entry \
  --host localhost --port 10002
```

**Launch the CLI (cmd.py)**
```bash
python3 -m app.cmd.cmd --agent http://localhost:10002
```



