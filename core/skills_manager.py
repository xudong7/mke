# core/skills_manager.py
import json
from pathlib import Path

class SkillManager:
    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills = self._load_skills()

    def _load_skills(self):
        skills = {}
        for f in self.skills_dir.glob("*.json"):
            with f.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
                skills[data["name"]] = data
        return skills

    def get_prompt_blocks(self, skill_names):
        blocks = []
        for name in skill_names:
            skill = self.skills.get(name)
            if skill and "prompt_block" in skill:
                blocks.append(skill["prompt_block"])
        return "\n\n".join(blocks)

    def list_skills(self):
        return list(self.skills.keys())
