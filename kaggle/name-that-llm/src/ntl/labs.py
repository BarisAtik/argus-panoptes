"""The 18 candidate models by lab, from a public guide to the competition.

Unconfirmed until real train.csv is here. `lab_accuracy` raises if a name is missing, so a mismatch
fails loudly rather than quietly scoring the wrong thing.
"""
from __future__ import annotations

LABS = {
    "OpenAI": ("gpt-5.5", "gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-6-astra"),
    "Google": ("gemini-3.1-pro-preview", "gemini-3.6-flash", "gemini-3.7-flash",
               "gemini-3.8-flash"),
    "Anthropic": ("claude-fable-5", "claude-opus-4-6", "claude-opus-4-8", "claude-opus-5",
                  "claude-sonnet-5"),
    "Qwen": ("qwen3.8-max",),
    "ZAI": ("glm-5.3", "glm-5.3-flash"),
    "Moonshot AI": ("kimi-k3",),
}
LAB_OF = {model: lab for lab, models in LABS.items() for model in models}
