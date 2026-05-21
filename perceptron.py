import math
import random


class Perceptron:

    def __init__(self, size: int):
        self.size = size
        self.bias = random.uniform(-1, 1)
        self.weights = [random.uniform(-1, 1) for _ in range(size)]
        self.inputs = [0.0] * size

    def set_inputs(self, inputs: list[float]):
        if len(inputs) != self.size:
            raise ValueError("Size of inputs is not equal to size of weights")
        self.inputs = inputs

    def weighted_sum(self) -> float:
        return sum(self.inputs[i] * self.weights[i] for i in range(self.size))

    def activation_function(self, weighted_sum: float) -> float:
        return math.tanh(weighted_sum)

    def output(self, is_in_output_layer: bool) -> float:
        if is_in_output_layer:
            return self.weighted_sum() + self.bias
        return self.activation_function(self.weighted_sum() + self.bias)
