"""Shared test fixtures — real-looking articles and expected outputs."""
from newstome.fetch import Article
from newstome.summarize import Summary

ARTICLES = [
    Article(
        title="RBI raises repo rate by 25 basis points to 6.75% amid inflation concerns",
        url="https://example.com/rbi-rate-hike",
        published="2025-04-22T06:00:00Z",
        content=(
            "The Reserve Bank of India on Tuesday raised the benchmark repo rate by 25 basis points "
            "to 6.75 percent, its second consecutive hike this fiscal year, as policymakers battle "
            "sticky headline inflation that has stayed above the 5 percent tolerance band for three "
            "straight months. The Monetary Policy Committee voted 5-1 in favour of the increase. "
            "Governor Shaktikanta Das said the decision was calibrated and data-dependent, adding "
            "that the central bank remains committed to anchoring inflation expectations while "
            "supporting growth. GDP growth for FY26 is projected at 6.8 percent. Home loan and "
            "auto loan EMIs are expected to rise by Rs 300-600 per lakh over a 20-year tenure."
        ),
        source="The Hindu",
        category="india_markets",
        trust=0.9,
    ),
    Article(
        title="OpenAI releases GPT-5 with multimodal reasoning and 1M token context",
        url="https://example.com/gpt5-release",
        published="2025-04-22T08:00:00Z",
        content=(
            "OpenAI on Wednesday unveiled GPT-5, its most capable model to date, featuring native "
            "multimodal reasoning across text, images, audio, and video alongside a one-million-token "
            "context window. The model scores 92 percent on the MMLU benchmark, up from GPT-4's 86 "
            "percent. CEO Sam Altman described it as a step toward artificial general intelligence. "
            "GPT-5 will be available to ChatGPT Plus subscribers immediately, with API access rolling "
            "out over the next two weeks. Pricing starts at $15 per million input tokens."
        ),
        source="TechCrunch",
        category="global_tech",
        trust=0.85,
    ),
    Article(
        title="ISRO successfully launches 50th PSLV mission carrying EOS-09 earth observation satellite",
        url="https://example.com/isro-pslv-50",
        published="2025-04-22T09:30:00Z",
        content=(
            "India's space agency ISRO on Thursday marked its 50th PSLV launch by placing the "
            "EOS-09 earth observation satellite into a 526-km sun-synchronous orbit. The satellite "
            "carries a synthetic aperture radar payload capable of imaging through clouds and at "
            "night, useful for agriculture monitoring and disaster response. The mission also "
            "carried five international co-passenger satellites. The launch took place at 9:17 AM "
            "from Satish Dhawan Space Centre, Sriharikota, and was declared a complete success "
            "by Mission Director S. Mohan Kumar."
        ),
        source="NDTV",
        category="india_science",
        trust=0.88,
    ),
]

GOOD_SUMMARIES = [
    Summary(
        headline="RBI hikes repo rate to 6.75 percent amid persistent inflation",
        body=(
            "The Reserve Bank of India raised its benchmark rate by 25 basis points to 6.75 percent, "
            "its second hike this fiscal year. The MPC voted 5-1 as headline inflation remained above "
            "5 percent for three months."
        ),
        url=ARTICLES[0].url,
        source=ARTICLES[0].source,
        category=ARTICLES[0].category,
        date=ARTICLES[0].published,
    ),
    Summary(
        headline="OpenAI launches GPT-5 with one million token context window",
        body=(
            "OpenAI released GPT-5 featuring native multimodal reasoning and a one-million-token context window. "
            "The model scores 92 percent on MMLU benchmark. API access starts at fifteen dollars per million input tokens."
        ),
        url=ARTICLES[1].url,
        source=ARTICLES[1].source,
        category=ARTICLES[1].category,
        date=ARTICLES[1].published,
    ),
]

BAD_SUMMARIES = [
    Summary(
        headline="In a recent development the central bank has now decided something",  # >10 words, filler
        body="The RBI did something. " * 12,  # way over 40 words
        url=ARTICLES[0].url,
        source=ARTICLES[0].source,
        category=ARTICLES[0].category,
        date=ARTICLES[0].published,
    ),
    Summary(
        headline="wow amazing AI news!!!",  # clickbait + emoji-adjacent exclamation
        body="OpenAI released GPT-5 today.",  # under 30 words
        url=ARTICLES[1].url,
        source=ARTICLES[1].source,
        category=ARTICLES[1].category,
        date=ARTICLES[1].published,
    ),
]
