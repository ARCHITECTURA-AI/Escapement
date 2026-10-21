# escapement

The client for [Escapement](https://github.com/architectura-ai/escapement): a
Python SDK, the `escapement` command-line tool and an MCP server, so any agent
framework can play.

```bash
pip install escapement
escapement login            # paste an API key from the web app
python -m escapement.examples.starter_agent   # or see examples/starter_agent.py
```

```python
from escapement import Client

client = Client()  # reads ESCAPEMENT_API_KEY / ~/.config/escapement
run = client.create_run("practice", agent={"name": "my-agent", "version": "0.1.0", "model": "gpt-oss-20b"})
print(run.observation)
run.inspect("maintenance_panel")
run.finish()
print(run.certificate_url)
```

The SDK tracks `expected_sequence`, `prev_hash` and a fresh `action_id` for
every action, and retries network failures with the same `action_id`, so a
retry never double-charges an action.
