from google.adk.agents import LlmAgent

from .config import get_model, load_prompt

# Skeleton only: tools (ingest, figure extraction, pptx build) and sub-agents
# (analyst, planner, writer) are added as they are implemented.
root_agent = LlmAgent(
    name="slide_root",
    model=get_model("root"),
    description="논문 PDF를 받아 발표용 PPT 슬라이드를 만들어 주는 진행자.",
    instruction=load_prompt("root"),
)
