from agents.extract_common import ExtractorAgent
from agents.io import RegistryOutput


class BrRegistryAgent(ExtractorAgent):
    name = "Br"
    prompt_file = "br_registry.md"
    output_model = RegistryOutput
    item_types = []

    def types(self) -> list[str]:
        return []

    def system_prompt(self) -> str:
        from agents.base import Agent, read_prompt
        return Agent.system_prompt(self) + "\n\n" + read_prompt("_extraction_guide.md")

    def extract(self, sources, registry=None):
        from agents.extract_common import sources_text
        return self.call(sources_text(sources) + "\n\nExtract the problem registry from the sources above.",
                         label="extract")
