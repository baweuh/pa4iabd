import numpy as np

from neural_network import NeuralNetwork


class GeneticNetwork(NeuralNetwork):
    def __init__(
        self,
        input_layer_size: int,
        hidden_layer_sizes: "int | list[int]",
        output_layer_size: int,
    ):
        super().__init__(input_layer_size, hidden_layer_sizes, output_layer_size)
        self.fitness: float = 0.0
        self.exponent: int = 4
        self.max_fitness: float = 0.0
        self.threshold: float = 0.25
        self.food_counter = 0

    def calculate_fitness(self, inputs: list[float], expected_outputs: list[float]):
        self.max_fitness = len(expected_outputs) ** self.exponent
        self.set_input_values(inputs)
        outputs = self.forward()
        correct_predictions = sum(
            1
            for i in range(len(outputs))
            if (expected_outputs[i] - outputs[i]) ** 2 < self.threshold
        )
        self.food_counter = correct_predictions
        self.fitness = correct_predictions**self.exponent
