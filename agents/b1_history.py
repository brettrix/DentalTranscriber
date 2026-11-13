from agents.extract_common import ExtractorAgent
from agents.io import ItemsOutput


class B1MedicalHistoryAgent(ExtractorAgent):
    name = "B1"
    prompt_file = "b1_history.md"
    output_model = ItemsOutput
