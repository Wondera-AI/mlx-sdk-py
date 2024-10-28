from pydantic import BaseModel, ConfigDict


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(**data)
        except Exception as e:
            raise ValueError(f"Error parsing input: {e}") from e

    def get_input_schema(self):
        return self.model_json_schema()


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(**data)
        except Exception as e:
            raise ValueError(f"Error parsing config: {e}") from e

    def get_output_schema(self):
        return self.model_json_schema()


class Output(BaseModel):
    def get_output_schema(self):
        return self.model_json_schema()
