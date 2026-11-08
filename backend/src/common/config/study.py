from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from typing import Self


class StudyConfig(BaseModel):
    desired_retention: float = Field(default=0.9, gt=0, lt=1)
    learning_step_seconds: int = Field(default=60, gt=0)
    relearning_step_seconds: int = Field(default=600, gt=0)
    learn_ahead_seconds: int = Field(default=1200, gt=0)
    maximum_interval: int = Field(default=36500, gt=0)
    enable_fuzzing: bool = True

    @model_validator(mode="after")
    def learning_steps_fit_ahead_window(self) -> Self:

        if self.learn_ahead_seconds * 2 < 3 * max(
            self.learning_step_seconds, self.relearning_step_seconds
        ):
            raise ValueError("Learn-ahead must cover all short learning steps.")
        return self
