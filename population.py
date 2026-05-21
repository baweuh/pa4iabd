import numpy as np
from genetic_network import GeneticNetwork


class Population:

    def __init__(self, size: int):
        self.size = size
        self.mutation_rate: float = 0.05
        self.generation: int = 0

        self.pop: list[GeneticNetwork] = [GeneticNetwork(1, [1], 1) for _ in range(size)]
        self.next_gen: list[GeneticNetwork | None] = [None] * size

        self.input_layer_size: int = 1
        self.hidden_layer_sizes: list[int] = [1]
        self.output_layer_size: int = 1

    def set_mutation_rate(self, mutation_rate: float):
        self.mutation_rate = mutation_rate

    def init_population(self,
                        input_layer_size: int,
                        hidden_layer_sizes: "int | list[int]",
                        output_layer_size: int):
        if isinstance(hidden_layer_sizes, int):
            hidden_layer_sizes = [hidden_layer_sizes]
        self.input_layer_size   = input_layer_size
        self.hidden_layer_sizes = hidden_layer_sizes
        self.output_layer_size  = output_layer_size
        self.pop = [
            GeneticNetwork(input_layer_size, hidden_layer_sizes, output_layer_size)
            for _ in range(self.size)
        ]

    def fitness_sum(self) -> float:
        return sum(individual.fitness for individual in self.pop)

    def select(self) -> GeneticNetwork:
        """Fitness-proportionate selection."""
        fitnesses = np.array([ind.fitness for ind in self.pop], dtype=np.float64)
        total = fitnesses.sum()
        if total <= 0:
            return self.pop[np.random.randint(self.size)]
        probs = fitnesses / total
        idx   = np.searchsorted(np.cumsum(probs), np.random.random())
        return self.pop[min(idx, self.size - 1)]

    def crossover(self, parent1: GeneticNetwork, parent2: GeneticNetwork) -> GeneticNetwork:
        child = GeneticNetwork(self.input_layer_size, self.hidden_layer_sizes, self.output_layer_size)
        total_fitness = parent1.fitness + parent2.fitness
        p1_weight = parent1.fitness / total_fitness if total_fitness > 0 else 0.5

        for layer_idx in range(len(child.weights)):
            W1 = parent1.weights[layer_idx]
            W2 = parent2.weights[layer_idx]
            b1 = parent1.biases[layer_idx]
            b2 = parent2.biases[layer_idx]
            Wc = child.weights[layer_idx]
            bc = child.biases[layer_idx]

            # Vectorised crossover: boolean mask selects from parent1 or parent2
            mask_w = np.random.random(W1.shape) < p1_weight
            Wc[:]  = np.where(mask_w, W1, W2)

            mask_b = np.random.random(b1.shape) < p1_weight
            bc[:]  = np.where(mask_b, b1, b2)

            # Vectorised mutation: random positions replaced with uniform(-1,1)
            mut_mask_w = np.random.random(Wc.shape) < self.mutation_rate
            Wc[mut_mask_w] = np.random.uniform(-1, 1, mut_mask_w.sum())

            mut_mask_b = np.random.random(bc.shape) < self.mutation_rate
            bc[mut_mask_b] = np.random.uniform(-1, 1, mut_mask_b.sum())

        return child

    def new_generation(self, inputs: list[float], expected_outputs: list[float]):
        for i in range(self.size):
            parent1 = self.select()
            parent2 = self.select()
            child = self.crossover(parent1, parent2)
            child.calculate_fitness(inputs, expected_outputs)
            self.next_gen[i] = child

    def replace_generation(self):
        self.pop = self.next_gen
        self.next_gen = [None] * self.size
        self.generation += 1

    def get_fittest(self) -> GeneticNetwork:
        return max(self.pop, key=lambda individual: individual.fitness)
