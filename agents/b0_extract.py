from agents.extract_common import ExtractorAgent
from agents.io import FullOutput


class B0ExtractionAgent(ExtractorAgent):
    name = "B0"
    prompt_file = "b0_extract.md"
    output_model = FullOutput
