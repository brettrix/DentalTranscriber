from agents.extract_common import ExtractorAgent
from agents.io import ItemsOutput


class B3FindingsAgent(ExtractorAgent):
    name = "B3"
    prompt_file = "b3_findings.md"
    output_model = ItemsOutput
