import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import anthropic
import requests
import re
from datetime import datetime


def regroup_transcript(raw_text):
    import re
    # Join all chunks into one string
    text = " ".join(raw_text.split("\n"))
    # Strip common caption artifacts like >>, [music], [applause] etc
    text = re.sub(r'>>+', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Split on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Capitalize first letter of each sentence and strip whitespace
    cleaned = []
    for s in sentences:
        s = s.strip()
        if s:
            s = s[0].upper() + s[1:]
            cleaned.append(s)
    # Join with double newline for breathing room
    return "\n\n".join(cleaned)


def get_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def get_video_info(video_id, api_key):
    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet",
                "id": video_id,
                "key": api_key
            }
        )
        data = response.json()
        snippet = data["items"][0]["snippet"]
        return {
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "date": snippet["publishedAt"][:10],
            "thumbnail": snippet["thumbnails"]["medium"]["url"]
        }
    except:
        return {
            "title": "Unknown Title",
            "channel": "Unknown Channel",
            "date": "",
            "thumbnail": None
        }


def get_top_comments(video_id, api_key, max_results=100):
    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "maxResults": max_results,
                "order": "relevance",
                "key": api_key
            }
        )
        data = response.json()
        if "error" in data:
            return None
        comments = []
        for item in data.get("items", []):
            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            likes = item["snippet"]["topLevelComment"]["snippet"]["likeCount"]
            comments.append({"text": comment, "likes": likes})
        return comments
    except:
        return None


PROMPTS = {
    "Summary": """Write a summary of this transcript in under 500 words.
Cover the main topic, key points, and overall conclusion.
Write in clear flowing prose, not bullet points.
Do not include a header or title in your response.""",

    "Top 10 Insights": """Extract the 10 most valuable insights from this transcript.
Include key ideas, frameworks, and concepts worth remembering.
Format as a numbered list with a brief explanation for each.
Do not include a header or title in your response.""",

    "Links & Resources": """Extract only concrete, specific resources from this transcript:
- Actual URLs or websites mentioned
- Specific tools or software products
- Books or publications by name
- Specific platforms or apps

Do NOT include: people's names, company names (unless they are the resource itself), vague references, or anything that isn't a specific actionable resource.

For each item:
- Name it clearly
- If it's a URL that may have been garbled in transcription, suggest the correct version
- One line on why it was mentioned

Keep the list tight. If fewer than 10 clear resources exist, only list what's there.
Do not include a header or title in your response.""",

    "Top 10 Comments": None,

    "Full Transcript": None
}

st.set_page_config(page_title="xtrudr", page_icon="⚡", layout="centered")

st.markdown("""
<head>
<meta property="og:title" content="xtrudr" />
<meta property="og:description" content="Paste any YouTube video. Get a summary, key insights, top comments, and more — in seconds." />
<meta property="og:image" content="https://raw.githubusercontent.com/eddelage/xtrudr/main/xtrudr.jpg" />
<meta property="og:url" content="https://xtrudr.streamlit.app" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="https://raw.githubusercontent.com/eddelage/xtrudr/main/xtrudr.jpg" />
</head>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Run button */
.stButton > button {
    background-color: #8b2010 !important;
    color: #ffffff !important;
    border: none !important;
}
.stButton > button:hover {
    background-color: #6b1608 !important;
}

/* Download button */
.stDownloadButton > button {
    background-color: #3d2b1f !important;
    color: #ffffff !important;
    border: none !important;
}
</style>
""", unsafe_allow_html=True)

st.title("⚡ xtrudr ⚡")
st.caption("Paste any YouTube video. Get a summary, key insights, top comments, and more — in seconds.")

url = st.text_input("Paste a YouTube URL")
modes = st.multiselect("What do you want?", list(PROMPTS.keys()), default=list(PROMPTS.keys()))
st.caption("All sections selected by default — click the ✕ to remove any you don't need.")

if st.button("Run", type="primary"):
    if not url:
        st.warning("Paste a YouTube URL first.")
    elif not modes:
        st.warning("Pick at least one option.")
    else:
        video_id = get_video_id(url)
        if not video_id:
            st.error("Couldn't find a valid YouTube video ID in that URL.")
        else:
            youtube_api_key = st.secrets["YOUTUBE_API_KEY"]
            anthropic_api_key = st.secrets["ANTHROPIC_API_KEY"]

            with st.spinner("Fetching video info..."):
                info = get_video_info(video_id, youtube_api_key)

            needs_transcript = any(m not in ["Top 10 Comments"] for m in modes)
            full_text = ""

            if needs_transcript:
                with st.spinner("Fetching transcript..."):
                    try:
                        ytt = YouTubeTranscriptApi()
                        transcript = ytt.fetch(video_id)
                        raw_text = "\n".join([entry.text for entry in transcript])
                        full_text = regroup_transcript(raw_text)
                    except Exception as e:
                        st.error("⚠️ No transcript available for this video. This can happen when captions are disabled, the video is private, or it's in a language without auto-captions.")
                        if any(m == "Top 10 Comments" in modes for m in modes):
                            st.info("You can still fetch Top 10 Comments — deselect the other options and try again.")
                        st.stop()

            all_outputs = {}

            # Use a placeholder to show progressive results during Run
            results_placeholder = st.empty()
            with results_placeholder.container():
                if info["thumbnail"]:
                    st.image(info["thumbnail"], use_container_width=False)
                st.markdown(f"**{info['channel']}**")
                st.markdown(f"### {info['title']}")
                if info["date"]:
                    st.caption(f"Published {info['date']}")
                st.markdown(f"[{url}]({url})")
                st.markdown("---")

                for mode in modes:
                    st.markdown(f"### {mode}")

                    if mode == "Full Transcript":
                        output = full_text
                        with st.expander("Show Full Transcript"):
                            st.text(full_text)

                    elif mode == "Top 10 Comments":
                        with st.spinner("Fetching comments..."):
                            comments = get_top_comments(video_id, youtube_api_key)
                        if comments is None:
                            st.warning("Comments are disabled or unavailable for this video.")
                            output = "Comments unavailable."
                        else:
                            comments_text = "\n\n".join([f"[{c['likes']} likes] {c['text']}" for c in comments])
                            client = anthropic.Anthropic(api_key=anthropic_api_key)
                            with st.spinner("Analyzing comments..."):
                                response = client.messages.create(
                                    model="claude-opus-4-5",
                                    max_tokens=1500,
                                    messages=[{"role": "user", "content": f"""From these YouTube comments, extract the 10 most insightful, interesting, or valuable ones.
Prioritize substance over hype. Skip generic praise like 'great video'.
Format as a numbered list with the comment followed by one line on why it's notable.
Do not include a header or title in your response.

Comments:
{comments_text}"""}]
                                )
                                output = response.content[0].text
                            st.markdown(output.replace("$", "\\$"))

                    else:
                        with st.spinner(f"Analyzing {mode}..."):
                            client = anthropic.Anthropic(api_key=anthropic_api_key)
                            response = client.messages.create(
                                model="claude-opus-4-5",
                                max_tokens=2000,
                                messages=[{"role": "user", "content": f"{PROMPTS[mode]}\n\nTranscript:\n{full_text}"}]
                            )
                            output = response.content[0].text
                        st.markdown(output.replace("$", "\\$"))

                    all_outputs[mode] = output
                    st.markdown("---")

            # Save everything to session state once done
            st.session_state["results"] = all_outputs
            st.session_state["info"] = info
            st.session_state["url"] = url
            st.session_state["full_text"] = full_text
            st.session_state["modes"] = modes
            results_placeholder.empty()

# Render results + download from session state (persists across rerenders)
if "results" in st.session_state:
    info = st.session_state["info"]
    all_outputs = st.session_state["results"]
    full_text = st.session_state["full_text"]
    modes = st.session_state["modes"]
    url = st.session_state["url"]

    if info["thumbnail"]:
        st.image(info["thumbnail"], use_container_width=False)
    st.markdown(f"**{info['channel']}**")
    st.markdown(f"### {info['title']}")
    if info["date"]:
        st.caption(f"Published {info['date']}")
    st.markdown(f"[{url}]({url})")
    st.markdown("---")

    for mode in modes:
        st.markdown(f"### {mode}")
        output = all_outputs.get(mode, "")

        if mode == "Full Transcript":
            with st.expander("Show Full Transcript"):
                st.text(output)
        elif mode == "Top 10 Comments":
            if output == "Comments unavailable.":
                st.warning("Comments are disabled or unavailable for this video.")
            else:
                st.markdown(output.replace("$", "\\$"))
        else:
            st.markdown(output.replace("$", "\\$"))

        st.markdown("---")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"xtrudr_{timestamp}.txt"
    download_content = f"Channel: {info['channel']}\nTitle: {info['title']}\nDate: {info['date']}\nSource: {url}\nExported: {timestamp}\n\n"
    for mode, output in all_outputs.items():
        download_content += f"{'='*50}\n{mode.upper()}\n{'='*50}\n\n{output}\n\n"
    if full_text and "Full Transcript" not in modes:
        download_content += f"{'='*50}\nFULL TRANSCRIPT\n{'='*50}\n\n{full_text}"

    st.download_button(
        label="Download All",
        data=download_content,
        file_name=filename,
        mime="text/plain"
    )

st.markdown("---")
st.caption("Got feedback? [Share your thoughts →](https://forms.gle/8dAYRQ8Xh3Pz5dYs8)")
st.caption("xtrudr © 2026")