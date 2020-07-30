# Copyright 2020 The TensorFlow Quantum Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Test parameter shift gradients over the TFQ sampling op."""
import copy

import numpy as np
import sympy
import tensorflow as tf
from absl.testing import parameterized

import cirq
from tensorflow_quantum.core.ops import circuit_execution_ops
from tensorflow_quantum.python import util
from tensorflow_quantum.python.differentiators import sampling_op_parameter_shift


def _cirq_evaluate_post_process(circuit_batch, resolvers, n_samples,
                                post_process_func):
    simulator = cirq.sim.Simulator()
    results = []
    for circuit, resolver in zip(circuit_batch, resolvers):
        state = simulator.simulate(circuit, resolver).final_state
        qubits = sorted(circuit.all_qubits())
        raw_results = cirq.sample_state_vector(
            state, len(qubits), repetitions=n_samples).astype(np.int32)
        results.append(post_process_func(raw_results))
    return results


def _cirq_simple_finite_difference(circuit_batch,
                                   resolvers,
                                   symbol_names,
                                   n_samples,
                                   post_process_func_list,
                                   grid_spacing=0.0001):
    """A simple finite difference code that calculates the gradient of a
    batch of circuits using cirq."""
    init_vals_list = _cirq_evaluate_post_process(
        circuit_batch, resolvers, n_samples, post_process_func_list)
    initial_values = np.asarray([[val for _, _ in enumerate(symbol_names)]
                      for val in init_vals_list])

    perturbed_values = []
    for this_program, this_resolver, this_func in zip(
            circuit_batch, resolvers, post_process_func_list):
        perturbed_values_circuit = []
        for symbol in symbol_names:
            perturbed_resolver = copy.deepcopy(this_resolver)
            perturbed_resolver.param_dict[symbol] += grid_spacing
            perturbed_values_circuit.append(_cirq_evaluate_post_process(
                this_program, perturbed_resolver, n_samples, this_func))
        perturbed_values.append(perturbed_values_circuit)
    perturbed_values = np.asarray(perturbed_values)

    return (1 / grid_spacing) * (perturbed_values - initial_values)


class GradientCorrectnessTest(tf.test.TestCase, parameterized.TestCase):
    """Test correctness of the differentiators to reference cirq algorithm."""

    @parameterized.parameters([{
        'sim': sim
    } for sim in [None, cirq.sim.sparse_simulator.Simulator(),
                  cirq.sim.density_matrix_simulator.DensityMatrixSimulator()]])
    def test_backprop(self, sim):
        """Compare utility sample-op gradients to analytic gradients."""

        def exact_grad(theta):
            new_theta = 2 * np.pi * theta
            return -2 * np.pi * np.sin(new_theta) * np.exp(np.cos(new_theta))

        @tf.function
        def post_process_func(bitstrings):
            """Emulate a Z measurement."""
            total_spin = tf.constant(0, dtype=tf.dtypes.float32)
            count = tf.cast(tf.math.multiply(
                tf.shape(bitstrings)[0], tf.shape(bitstrings)[1]), tf.float32)
            for i in tf.range(tf.shape(bitstrings)[0]):
                for j in tf.range(tf.shape(bitstrings)[1]):
                    total_spin = tf.add(
                        total_spin, tf.cast(1 - bitstrings[i][j]*2, tf.float32))
            return total_spin / count

        op = sampling_op_parameter_shift.get_sample_op_postprocessor(
            backend=None, post_process_func=post_process_func)

        bit = cirq.GridQubit(0, 0)
        circuits = util.convert_to_tensor(
            [cirq.Circuit(cirq.X(bit)**sympy.Symbol('rx')) for _ in range(2)])
        base_rot_angles = tf.constant([[0.25], [0.125]])
        repetitions = 1000
        with tf.GradientTape() as g:
            g.watch(base_rot_angles)
            input_angles = 2 * base_rot_angles
            exp_res = tf.exp(op(circuits, ['rx'], input_angles, [repetitions]))

        grad = g.gradient(exp_res, base_rot_angles)
        exact = [[exact_grad(0.25)], [exact_grad(0.125)]]

        # will this be too tight? time will tell.
        self.assertAllClose(exact, grad.numpy(), rtol=0.01, atol=0.01)

    # @parameterized.parameters(
    #     list(
    #         util.kwargs_cartesian_product(
    #             **{
    #                 'differentiator': DIFFS,
    #                 'op': OPS,
    #                 'n_qubits': [5],
    #                 'n_programs': [3],
    #                 'n_ops': [3],
    #                 'symbol_names': [['a', 'b']]
    #             })))
    # def test_gradients_vs_cirq_finite_difference(self, differentiator, op,
    #                                              n_qubits, n_programs, n_ops,
    #                                              symbol_names):
    #     """Compare TFQ differentiators to fine-grained noiseless cirq finite
    #     differencing.
    #     DISCLAIMER : the consistency of STOCHASTIC_DIFFS is hard to be checked.
    #     Its expectation value should be checked, but it takes long time because
    #     SGDifferentiator is not optimized. Until optimized, the consistency
    #     will be performed in benchmarks/scripts/differentiators:convergence_test
    #     TODO(jaeyoo) : move convergence_test here once SGDifferentiator is
    #      optimized.
    #     """
    #     differentiator.refresh()
    #     op = differentiator.generate_differentiable_op(analytic_op=op)

    #     qubits = cirq.GridQubit.rect(1, n_qubits)
    #     circuit_batch, resolver_batch = \
    #         util.random_symbol_circuit_resolver_batch(
    #             cirq.GridQubit.rect(1, n_qubits), symbol_names, n_programs)

    #     psums = [
    #         util.random_pauli_sums(qubits, 1, n_ops) for _ in circuit_batch
    #     ]

    #     symbol_values_array = np.array(
    #         [[resolver[symbol]
    #           for symbol in symbol_names]
    #          for resolver in resolver_batch],
    #         dtype=np.float32)

    #     # calculate tfq gradient
    #     symbol_values_tensor = tf.convert_to_tensor(symbol_values_array)
    #     programs = util.convert_to_tensor(circuit_batch)
    #     ops = util.convert_to_tensor(psums)
    #     with tf.GradientTape() as g:
    #         g.watch(symbol_values_tensor)
    #         expectations = op(programs, symbol_names, symbol_values_tensor, ops)
    #     tfq_grads = g.gradient(expectations, symbol_values_tensor)

    #     # calculate gradients in cirq using a very simple forward differencing
    #     # scheme
    #     cirq_grads = _cirq_simple_finite_difference(circuit_batch,
    #                                                 resolver_batch,
    #                                                 symbol_names, psums)

    #     # will this be too tight? time will tell.
    #     self.assertAllClose(cirq_grads, tfq_grads, rtol=1e-2, atol=1e-2)

    # @parameterized.parameters(
    #     list(
    #         util.kwargs_cartesian_product(
    #             **{
    #                 'differentiator': DIFFS + STOCHASTIC_DIFFS,
    #                 'op': OPS,
    #                 'stochastic_cost': [False, True]
    #             })))
    # def test_analytic_value_with_simple_circuit(self, differentiator, op,
    #                                             stochastic_cost):
    #     """Test the value of differentiator with simple circuit.
    #     Since there are only one symbol, one gate and one op, there is only one
    #     samling result, STOCHATIC_DIFFS shows the same result with that of
    #     deterministic differentiators."""
    #     # Get an expectation op, with this differentiator attached.
    #     differentiator.refresh()
    #     differentiator.stochastic_cost = stochastic_cost
    #     op = differentiator.generate_differentiable_op(analytic_op=op)
    #     qubit = cirq.GridQubit(0, 0)
    #     circuit = util.convert_to_tensor(
    #         [cirq.Circuit(cirq.X(qubit)**sympy.Symbol('alpha'))])
    #     psums = util.convert_to_tensor([[cirq.Z(qubit)]])
    #     symbol_values_array = np.array([[0.123]], dtype=np.float32)
    #     # Calculate tfq gradient.
    #     symbol_values_tensor = tf.convert_to_tensor(symbol_values_array)
    #     with tf.GradientTape() as g:
    #         g.watch(symbol_values_tensor)
    #         expectations = op(circuit, ['alpha'], symbol_values_tensor, psums)
    #     grads = g.gradient(expectations, symbol_values_tensor)
    #     ground_truth_grads = np.array([[-1.1839752]])
    #     self.assertAllClose(ground_truth_grads, grads, rtol=1e-2, atol=1e-2)


if __name__ == '__main__':
    tf.test.main()
