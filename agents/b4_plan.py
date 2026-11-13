from agents.extract_common import ExtractorAgent
from agents.io import ItemsOutput


class B4PlanAgent(ExtractorAgent):
    name = "B4"
    prompt_file = "b4_plan.md"
    output_model = ItemsOutput
