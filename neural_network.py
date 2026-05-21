import numpy as np


class NeuralNetwork:
    """
    Feed-forward network backed by numpy weight matrices.

    Parameters
    ----------
    input_layer_size   : number of input neurons
    hidden_layer_sizes : list of hidden layer widths, e.g. [16, 8]
                         A single int is also accepted for backwards compatibility.
    output_layer_size  : number of output neurons

    Internal structure
    ------------------
    self.weights : list of np.ndarray, shape (out, in)  — one per layer incl. output
    self.biases  : list of np.ndarray, shape (out,)

    Forward pass per layer:
        hidden : tanh(W @ x + b)
        output : W @ x + b          (linear, no activation)
    """

    def __init__(self,
                 input_layer_size: int,
                 hidden_layer_sizes: "int | list[int]",
                 output_layer_size: int):

        if isinstance(hidden_layer_sizes, int):
            hidden_layer_sizes = [hidden_layer_sizes]

        self.input_layer_size   = input_layer_size
        self.hidden_layer_sizes = list(hidden_layer_sizes)
        self.output_layer_size  = output_layer_size

        # Build weight matrices and bias vectors
        self.weights: list[np.ndarray] = []
        self.biases:  list[np.ndarray] = []

        sizes = [input_layer_size] + list(hidden_layer_sizes) + [output_layer_size]
        for i in range(len(sizes) - 1):
            self.weights.append(np.random.uniform(-1, 1, (sizes[i+1], sizes[i])))
            self.biases.append( np.random.uniform(-1, 1, (sizes[i+1],)))

        # Input buffer
        self._input: np.ndarray = np.zeros(input_layer_size)

    # ------------------------------------------------------------------
    def set_input_values(self, inputs: "list[float] | np.ndarray"):
        if len(inputs) != self.input_layer_size:
            raise ValueError("Size of inputs is not equal to Neural Network's inputs size")
        self._input = np.asarray(inputs, dtype=np.float64)

    def forward(self) -> list[float]:
        x = self._input
        for i, (W, b) in enumerate(zip(self.weights, self.biases)):
            x = W @ x + b
            if i < len(self.weights) - 1:   # hidden layers: tanh activation
                x = np.tanh(x)
        return x.tolist()

    def predict(self, inputs: "list[float] | np.ndarray") -> list[float]:
        self.set_input_values(inputs)
        return self.forward()
