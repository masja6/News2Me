import time
from fastapi.testclient import TestClient
from newstome.ui import app
from newstome.pipeline import prepare_clusters, build_user_digest

def run_persona_tests():
    client = TestClient(app)
    
    personas = [
        {
            "name": "Captain Jack",
            "email": "pirate@test.com",
            "tone": "Dramatic Pirate",
            "jargon_busting": True,
            "cats": ["india_politics", "global_bigtech"]
        },
        {
            "name": "Market Whiz",
            "email": "analyst@test.com",
            "tone": "Wall Street Analyst",
            "jargon_busting": False,
            "cats": ["india_markets", "global_ai"]
        },
        {
            "name": "Little Jimmy",
            "email": "child@test.com",
            "tone": "ELI5 (Explain Like I'm Five)",
            "jargon_busting": True,
            "cats": ["global_ai", "global_oss"]
        }
    ]

    print("🚀 BOOTING PERSONA TEST SUITE")
    print("-------------------------------")
    
    # 1. Fetch news once for sharing across tests
    print("Step 1: Fetching global news clusters...")
    ranked = prepare_clusters(verbose=False)
    if not ranked:
        print("!! No news found. Check your RSS feeds.")
        return

    # 2. Iterate through personas
    for p in personas:
        print(f"\n[PERSONA] testing {p['name']} (Tone: {p['tone']}, Jargon: {p['jargon_busting']})")
        
        # Simulate registration
        payload = {
            "name": p["name"],
            "email": p["email"],
            "india_categories": [c for c in p["cats"] if c.startswith("india")],
            "global_categories": [c for c in p["cats"] if c.startswith("global")],
            "max_items": 3,
            "tone": p["tone"],
            "jargon_busting": p["jargon_busting"]
        }
        
        # Trigger subscription
        r = client.post("/subscribe", json=payload)
        if r.status_code == 200:
            print(f"  ✓ Subscribed successfully.")
        
        # Trigger generation logic manually (don't wait for background tasks)
        print(f"  Generating summaries...")
        summaries, _ = build_user_digest(ranked, payload, verbose=False)
        
        if not summaries:
            print("  ! No summaries generated.")
            continue
            
        for i, s in enumerate(summaries, 1):
            print(f"  --- Story {i} ---")
            print(f"  Headline: {s.headline}")
            print(f"  Body: {s.body}")
            if p["jargon_busting"] and "<abbr" in s.body:
                print("  [Verified] Jargon <abbr> found!")
            elif p["jargon_busting"]:
                print("  [Warn] Jargon busting ON but no <abbr> tags in this specific body.")

        # Delay to avoid Anthropic rate limits between personas
        time.sleep(5)

if __name__ == "__main__":
    run_persona_tests()
