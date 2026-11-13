from agents.extract_common import ExtractorAgent
from agents.io import ItemsOutput


class B2ComplaintAgent(ExtractorAgent):
    name = "B2"
    prompt_file = "b2_complaint.md"
    output_model = ItemsOutput
