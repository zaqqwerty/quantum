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
"""Layers for constructing qudit circuits on qubit backends."""
import numpy as np
import tensorflow as tf
import cirq

from tensorflow_quantum.core.ops import tfq_utility_ops
from tensorflow_quantum.python import util
from tensorflow_quantum.python.layers.circuit_executors import expectation


def projector_on_one(qubit):
    """Returns the projector on 1 for the given qubit.
 
    Given a qubit k, the projector onto one can be represented by
        |1><1|_k = 0.5(I_k - Z_k).

    Args:
        qubit: A `cirq.GridQubit` on which the projector is supported.
    
    Returns:
        `cirq.PauliSum` representing the projector.
    """
    if not isinstance(qubit, cirq.GridQubit):
        raise TypeError("A projector must live on a cirq.GridQubit.")
    return 0.5*cirq.I(qubit)-0.5*cirq.Z(qubit)


def integer_operator(qubits):
    """Returns operator representing position in binary on a qubit register.

    Unsigned integers on computers can be represented as a bitstring.  For an
    integer represented by N bits, the k-th bit represents the presence
    of the number 2**(N - k - 1) in the sum representing the integer.
    Similarly, we can define a binary operator J as
        J = \sum_P{k=0}^{N-1} 2^{N-k-1}|1><1|_k,
    where
        |1><1|_k = 0.5(I_k - Z_k).
    J can be represented by a `cirq.PauliSum`.

    Args:
        qubits: Python `list` of `GridQubit`s on which the operator is
            supported.

    Returns:
        int_op: A `cirq.PauliSum` representing the integer operator.
    """
    if not isinstance(qubits, list):
        raise TypeError("Argument qubits must be a list of cirq.GridQubits.")
    int_op = cirq.PauliSum()
    width = len(qubits)
    for loc, q in enumerate(qubits):
        int_op += 2**(width - 1 - loc) * projector_on_one(q)
    return int_op


def registers_from_precisions(precisions):
    """Returns list of cirq.GridQubit registers for the given precisions.

    Args:
        precisions: a Python `list` of `int`s.  Entry `precisions[i]` sets
            the number of qubits on which quantum integer `i` is supported.

    Returns:
        register_list: lists of `cirq.GridQubit`s, such that
            len(register_list[i]) == precisions[i] and all entries are unique.
    """
    if not isinstance(precisions, list):
        raise TypeError("Argument qubits must be a list of cirq.GridQubits.")
    register_list = []
    for r, width in enumerate(precisions):
        this_register = []
        for col in range(width):
            this_register.append(cirq.GridQubit(r, col))
        register_list.append(this_register)
    return register_list


def build_cost_psum(precisions, cliques):
    """Returns the cirq.PauliSum corresponding to the given cliques."""
    register_list = registers_from_precisions(precisions)
    op_list = [integer_operator(register) for register in register_list]
    cost_psum = cirq.PauliSum()
    for clique in cliques:
        this_psum = cirq.PauliString(cirq.I(register_list[clique[0]][0]))
        for i in clique:
            this_psum *= op_list[i]
        this_psum *= cliques[clique]
        cost_psum += this_psum
    return cost_psum


# class AppendCostExp(tf.keras.layers.Layer):
#     """Layer appending the exponential of quantum integer cost to input circuit.


#     Note: When specifying a new layer for a *compiled* `tf.keras.Model` using
#     something like
#     `tfq.layers.AppendCostExp()(cirq.Circuit(...), ...)`
#     please be sure to instead use
#     `tfq.layers.AppendCostExp()(circuit_input, ...)`
#     where `circuit_input` is a `tf.keras.Input` that is filled with
#     `tfq.conver_to_tensor([cirq.Circuit(..)] * batch_size)` at runtime. This
#     is because compiled Keras models require non keyword layer `call` inputs to
#     be traceable back to a `tf.keras.Input`.

#     """

#     def __init__(self, precisions, cost, **kwargs):
#         """Instantiate this layer."""
#         super().__init__(**kwargs)



#     def call(self, inputs, *, exp_symbol_name=None, exp_symbol_value=None):
#         """Keras call method.

#         Input options:
#             `inputs`, `precisions`, `cost`:
#                 see `layer_input_checks`

#         Output shape:
#             `tf.Tensor` of shape [batch_size] containing the exponential of the
#                 qudit cost appended to the input circuits.

#         """

#         inputs, precisions, cost = layer_input_check(inputs, precisions, cost)

        
#         batch_dim = tf.gather(tf.shape(inputs), 0)
#         if isinstance(append, cirq.Circuit):
#             append = tf.tile(util.convert_to_tensor([append]), [batch_dim])
#         else:
#             append = util.convert_to_tensor(append)

#         return tfq_utility_ops.tfq_append_circuit(inputs, append)
