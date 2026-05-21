from genetic_network import GeneticNetwork
from population import Population


class GeneticAlgorithm:

    def __init__(self, population_size: int, generations: int):
        self.hidden_layer_size: int = 64
        self.population_size: int = population_size
        self.generations: int = generations
        self.population: Population = Population(population_size)
        self.fittest: GeneticNetwork | None = None

    def train(self, inputs: list[float], expected_outputs: list[float]):
        self.population.init_population(len(inputs), self.hidden_layer_size, len(expected_outputs))
        for _ in range(self.generations):
            self.population.new_generation(inputs, expected_outputs)
            self.population.replace_generation()
        self.fittest = self.population.get_fittest()

    def get_fittest(self) -> GeneticNetwork | None:
        return self.fittest
