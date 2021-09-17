from __future__ import annotations
from abc import ABC, abstractmethod, abstractproperty
from itertools import product
from mrmustard import Backend
import numpy as np
backend = Backend()
from mrmustard._typing import *


class XPTensor:
    r"""A representation of Matrices and Vectors in phase space.

    Tensors in phase space have a (2n, 2n) or (2n,) shape where n is the number of modes.
    There are two main orderings:
        - xxpp: matrix is a `2\times 2` block matrix where each block is an `xx`, `xp`, `px`, `pp` block on all modes.
        - xpxp: matrix is a `n\times n` block matrix of `2\times 2` blocks each corresponding to a mode or a coherence between modes
    This creates some difficulties when we need to work in a mode-wise fashion, especially whith coherences.
    We solve this problem by reshaping the matrices to `(n,m,2,2)` and vectors to `(n,2)`.

    We call `n` the outmodes and `m` the inmodes.
    Off-diagonal matrices like coherences have all the outmodes different than the inmodes.
    Diagonal matrices like coviariances and symplectic transformations have the same outmodes as the inmodes.
    Vectors have only outmodes.

    XPTensor objects are sparse, in the sense that they support implicit operations between modes where one or more tensors are undefined.
    There are two types of behaviour:
        - like_0 (default): in modes where the tensor is undefined, it's like having a zero (a zero matrix)
        - like_1: in modes where the tensor is undefined, it's like having a one (an identity matrix)
    For example, in the expression X @ means + d where X is a symplectic matrix and d is a displacement vector,
    if X is undefined it's like having the identity and the matrix product simply returns means, while in the expression
    means + d if d is undefined it simply returns means. In this example no operation was actually computed.
    Thanks to sparsity we can represent graph states and transformations on graph states as XPTensor objects.

    Arguments:
        tensor: The tensor to be represented in (n,n,2,2) order.
        modes: a list of modes for a diagonal matrix or a vector and a tuple of lists for a coherence
        like_0: Whether the null tensor behaves like 0 for addition
        like_1: Whether the null tensor behaves like 1 for multiplication
    """

    def __init__(self,
                tensor: Optional[Tensor] = None,
                modes: Union[Sequence[int], Sequence[Sequence[int], Sequence[int]]] = ([], []),
                like_0=None, like_1=None):
        if like_0 is None and like_1 is None:
            raise ValueError("At least one of like_0 or like_1 must be set")
        self.like_0 = bool(like_0) or not bool(like_1)  # I love python
        self.shape = None if tensor is None else tensor.shape[:tensor.nmodes//2]  # only (n,m) or (n,)
        self.ndim = None if tensor is None else len(self.shape)
        self.isVector = None if tensor is None else self.ndim == 1
        self.tensor = tensor
        self.modes = self.validate_modes(modes)

    @property
    def dtype(self):
        return None if self.tensor is None else self.tensor.dtype

    @property
    def outmodes(self) -> List[int]:
        return self.modes[0]

    @property
    def inmodes(self) -> List[int]:
        return self.modes[1]

    @property
    def num_modes(self) -> int:
        'note this is meaningful only for diagonal matrices and vectors'
        return len(self.outmodes)

    @property
    def isMatrix(self) -> Optional[bool]:
        return None if self.tensor is None else not self.isVector

    @property
    def isCoherence(self) -> Optional[bool]:
        return None if self.tensor is None else self.isMatrix and self.outmodes != self.inmodes

    @property
    def like_1(self) -> bool:
        return not self.like_0

    @property
    def T(self) -> XPTensor:
        if self.isVector:
            raise ValueError("Cannot transpose a vector")
        if self.tensor is None:
            return self
        return XPTensor.from_tensor(backend.transpose(self.tensor, (1,0,3,2)), (self.inmodes, self.outmodes), self.like_0, self.like_1)

    def validate_modes(self, modes:Optional[Union[Sequence[int], Sequence[Sequence[int], Sequence[int]]]]) -> Tuple(List[int], List[int]):  # NOTE: call after setting isVector and tensor
        if modes is None:
            modes = ([], [])
        if all(isinstance(m, int) for m in modes):
            modes = (modes,) if self.isVector else (modes, modes)
        if len(modes[0]) == 0 and len(modes[1]) == 0 and self.tensor is not None:
            modes = tuple(list(range(s)) for s in (self.shape+(0,) if self.isVector else self.shape))
        assert set(modes[0]).isdisjoint(modes[1]) or set(modes[0]) == set(modes[1])
        return modes

    @classmethod
    def from_xxpp(cls,
    tensor: Union[Matrix, Vector],
    modes: Optional[Tuple[List[int],List[int]]] = ([], []),
    like_0: bool = None,
    like_1: bool = None) -> XPTensor:
        if tensor is not None:
            tensor = backend.reshape(tensor, [_ for n in tensor.shape for _ in (2, n//2)])
            tensor = backend.transpose(tensor, (1, 3, 0, 2)[:tensor.ndim])
        return XPTensor(tensor, modes, like_0, like_1)

    @classmethod
    def from_xpxp(cls,
    tensor: Union[Matrix, Vector],
    modes: Optional[Tuple[List[int], List[int]]] = ([], []),
    like_0: bool = None,
    like_1: bool = None) -> XPTensor:
        if tensor is not None:
            tensor = backend.reshape(tensor, [_ for n in tensor.shape for _ in (n//2, 2)])
            tensor = backend.transpose(tensor, (0, 2, 1, 3)[:tensor.ndim])
        return cls.from_tensor(tensor, modes, like_0, like_1)

    def to_xpxp(self) -> Optional[Matrix]:
        if self.tensor is None:
            return None
        tensor = backend.transpose(self.tensor, (0, 2, 1, 3) if self.isMatrix else (0, 1))
        return backend.reshape(tensor, [2 * s for s in self.shape])

    def to_xxpp(self) -> Optional[Tensor]:
        if self.tensor is None:
            return None
        tensor = backend.transpose(self.tensor, (2, 0, 3, 1) if self.isMatrix else (1, 0))
        return backend.reshape(self.tensor, [2 * s for s in self.shape])

    def __array__(self):
        return self.to_xxpp()

    def modes_first(self) -> Optional[Tensor]:
        return self.tensor
    
    def modes_last(self) -> Optional[Tensor]:
        if self.tensor is None:
            return None
        return backend.transpose(self.tensor, (2,3,0,1) if self.isMatrix else (0,1))  # 22NM or 2N

    def clone(self, times: int, modes=None) -> XPTensor:
        r"""Create a new XPTensor made by cloning the system a given number of times.
        The modes are reset by default unless specified.
        """
        if self.tensor is None:
            return self
        if self.isMatrix:
            tensor = backend.expand_dims(self.modes_last(), axis=4)  # shape = [2,2,N,N,1]
            tensor = backend.tile(tensor, (1, 1, 1, 1, times))  # shape = [2,2,N,N,T]
            tensor = backend.diag(tensor) # shape = [2,2,N,N,T,T]
            tensor = backend.transpose(tensor, (0, 1, 2, 4, 3, 5))  # shape = [2,2,N,T,N,T]
            tensor = backend.reshape(tensor, (2,2,other.num_modes,other.num_modes))  # shape = [2,2,NT,NT] = [2,2,O,O]
            tensor = backend.transpose(tensor, (2, 3, 0, 1))  # shape = [NT,NT,2,2]
        else:
            tensor = backend.tile(self.expand_dims(self.tensor.modes_last(), axis=2), (1, 1, times))  # shape = [2,N,T]
            tensor = backend.reshape(tensor, (2, -1))  # shape = [2,NT] = [2,O]
            tensor = backend.transpose(tensor, (1, 0))  # shape = [NT,2] = [O,2]
        return XPTensor(tensor, modes=modes, like_0=self.like_0, like_1=self.like_1)


    def clone_like(self, other: XPTensor):
        r"""
        Create a new XPTensor with the same shape and modes as other. The new tensor
        has the same content as self, cloned as many times as necessary to match the shape and modes of other.
        The other properties are kept as is.
        Arguments:
            other: The tensor to be cloned.
        Returns:
            A new XPTensor with the same shape and modes as other.
        """
        if other.shape == self.shape:
            return self
        if self.isCoherence:
            raise ValueError("Cannot clone a coherence block")
        if bool(other.num_modes % self.num_modes):
            raise ValueError(f"No multiple of {self.num_modes} modes fits into {other.num_modes} modes")
        times = other.num_modes//self.num_modes
        if self.isVector == other.isVector:
            tensor = self.clone(times, modes=other.modes)
        else:
            raise ValueError("Cannot clone a vector into a matrix or viceversa")
        return XPTensor(tensor, (other.outmodes, other.inmodes), self.like_0, self.like_1)

    ####################################################################################################################
    # Operators
    ####################################################################################################################

    def __rmul__(self, other: Scalar) -> XPTensor:
        'implements the operation self * other'
        if self.tensor is None:
            if self.like_1:
                raise NotImplementedError("Cannot multiply a scalar and a like_1 null tensor yet")
            else:
                return XPTensor(None, like_0=self.like_0, like_1=self.like_1)
        self.tensor = other * self.tensor
        return self

    def __mul__(self, other: Scalar) -> Optional[XPTensor]:
        return other * self if self.tensor is not None else None

    def __matmul__(self, other: XPTensor) -> Optional[XPTensor]:
        if not isinstance(other, XPTensor):
            raise TypeError("unsupported operand type(s) for @: 'XPTensor' and '{}'".format(type(other)))
        # both None
        if self.tensor is None and other.tensor is None:
            return XPTensor(like_1=self.like_1 * other.like_1)
        # either None
        if self.tensor is None:
            return self if self.like_0 else other
        if other.tensor is None:
            return other if other.like_0 else self
        # Now neither self nor other is None
        if self.isMatrix:
            tensor, modes = self._mode_aware_matmul(other)
        elif self.isVector and other.isMatrix:
            tensor, modes = other.T._mode_aware_matmul(self)
        else: # i.e. self.isVector and other.isVector:
            tensor, modes = self._mode_aware_vecvec(other)
        return XPTensor(tensor, modes, like_1=self.like_1 * other.like_1)

    def _mode_aware_matmul(self, other:XPTensor) -> Tuple[Tensor, Tuple[List[int], List[int]]]:
        r"""Performs matrix multiplication only on the necessary modes and
        takes care of keeping only the modes that are needed, in case of mismatch.
        See documentation for a visual explanation with coloured blocks.  #TODO: add link to figure
        """
        modes_match = list(self.inmodes) == list(other.outmodes)  # NOTE: they match including the ordering
        if modes_match:
            return backend.tensordot(self.tensor, other.tensor, ((2,3),(0,1))), (self.outmodes, other.inmodes)
        contracted = [i for i in self.inmodes if i in other.outmodes]
        uncontracted_other = [o for o in other.outmodes if o not in contracted]
        uncontracted_self = [i for i in self.inmodes if i not in contracted]
        outmodes = sorted(self.outmodes + uncontracted_other) if self.like_1 else self.outmodes  # NOTE mind to the sorting
        inmodes = sorted(other.inmodes + uncontracted_self) if other.like_1 else other.inmodes
        outmodes_repeated = len(set(outmodes)) != len(outmodes)
        inmodes_repeated = len(set(inmodes)) != len(inmodes)
        if outmodes_repeated or inmodes_repeated:
            raise ValueError("invalid modes")
        blue = None  # shape = [N1,M2,2,2]
        green = None # shape = [N1,M2,2,2]
        purple = None
        white = None  
        if len(contracted) > 0:
            blue = backend.tensordot(backend.gather(self.tensor, contracted, axis=1), backend.gather(other.tensor, contracted, axis=0), ((1,3),(0,2)))
        if self.like_1 and len(uncontracted_other) > 0:
            green = backend.gather(other.tensor, uncontracted_other, axis=0)
        if other.like_1 and len(uncontracted_self) > 0:
            purple = backend.gather(self.tensor, uncontracted_self, axis=1)
        if self.like_1 and other.like_1 and green is not None and purple is not None and blue is not None:
            white = backend.zeros((green.shape[0], purple.shape[1], 2, 2), dtype=blue.dtype)
        if green is not None and purple is not None:
            final = backend.block([[blue, green],[purple, white]], axes=[0,1])
        elif green is not None and purple is None:
            final = backend.block([[blue, green]], axes=[0,1])
        elif green is None and purple is not None:
            final = backend.block([[blue],[purple]], axes=[0,1])
        else:
            final = blue
        outmodes_transposition = [outmodes.index(o) for o in sorted(outmodes)]
        inmodes_transposition = [inmodes.index(i) for i in sorted(inmodes)]
        final = backend.gather(final, outmodes_transposition, axis=0)
        if len(inmodes_transposition) > 0:
            final = backend.gather(final, inmodes_transposition, axis=1)
        # NOTE: the order that we return is not the same thing as the transposition that obtains that order
        return final, (list(sorted(outmodes)), list(sorted(inmodes)))

    def _mode_aware_vecvec(self, other: XPTensor) -> Scalar:
        modes_match = list(self.outmodes) == list(other.outmodes)
        if modes_match:
            return backend.sum(self.tensor * other.tensor)
        common = list(set(self.outmodes) & set(other.outmodes))  # only the common modes (the others are like 0)
        return backend.sum(backend.gather(self.tensor, common, axis=0) * backend.gather(other.tensor, common, axis=0))

    def __add__(self, other: XPTensor) -> Optional[XPTensor]:
        if not isinstance(other, XPTensor):
            raise TypeError("unsupported operand type(s) for +: 'XPTensor' and '{}'".format(type(other)))
        if self.isVector != other.isVector:
            raise ValueError("Cannot add a vector to a matrix or viceversa")
        if self.isCoherence != other.isCoherence:
            raise ValueError("Cannot add a coherence block and a diagonal block")
        if self.tensor is None and other.tensor is None: # both are none
            if self.like_1 and other.like_1:
                raise ValueError("Cannot add two like_1 null tensors yet")  # because 1+1 = 2
            return XPTensor(like_1= self.like_1 or other.like_1) # 0+0 = 0, 1+0 = 1, 0+1=1
        if self.tensor is None:  # only self is None
            if self.like_0:
                return other
            return ValueError("1+other not implemented 🥸")
        if other.tensor is None:  # only other is None
            if other.like_0:
                return self
            return ValueError("self+1 not implemented 🥸")
        # now neither is None
        modes_match = list(self.outmodes) == list(other.outmodes) and list(self.inmodes) == list(other.inmodes)
        if modes_match:
            self.tensor = self.tensor + other.tensor
            return self
        outmodes = [o for o in self.outmodes if o not in other.outmodes]
        inmodes = [i for i in self.inmodes if i not in other.inmodes]
        self_contains_other = set(self.outmodes).issuperset(other.outmodes) and set(self.inmodes).issuperset(other.inmodes)
        other_contains_self = set(other.outmodes).issuperset(self.outmodes) and set(other.inmodes).issuperset(self.inmodes)
        if self_contains_other:
            to_update = self.tensor
            to_add = [other]
        elif other_contains_self:
            to_update = other.tensor
            to_add = [self]
        else:  # need to add both to a new empty tensor
            to_update = backend.zeros((len(outmodes), len(inmodes), 2, 2) if self.isMatrix else (len(outmodes), 2), dtype=self.tensor.dtype)
            to_add = [self, other]
        for t in to_add:
            outmodes_indices = [outmodes.index(o) for o in t.outmodes]
            inmodes_indices = [inmodes.index(i) for i in t.inmodes]
            if t.isMatrix: # e.g. outmodes of to_update are [self]+[other_new] = (e.g.) [9,1,2]+[0,20]
                indices = [[o,i] for o in outmodes_indices for i in inmodes_indices]
            else:
                indices = [[o] for o in outmodes_indices]
            to_update = backend.update_add_tensor(to_update, indices, backend.reshape(t.modes_first(),(-1,2,2) if self.isMatrix else (-1,2)))
        return XPTensor(to_update, modes, additive=self.like_0 and other.like_0, multiplicative=self.like_1 or other.like_1)

    def __sub__(self, other: XPTensor) -> Optional[XPTensor]:
        return self + (-1) * other

    def __truediv__(self, other: Scalar) -> Optional[XPTensor]:
        return (1/other) * self

    def __repr__(self) -> str:
        return (f"XPTensor(" + ("Matrix, " if self.isMatrix else "Vector, ") + ("coherence, " if self.isCoherence else "") +
                f"modes={self.modes}, " +
                f"like_0={self.like_0}, like_1={self.like_1},\n" +
                f"tensor_xpxp={self.to_xpxp()})")

    def __getitem__(self, item: Union[int, slice, List[int]]) -> Tensor:
        r"""
        Returns modes or subsets of modes from the XPTensor, or coherences between modes using an intuitive notation
        Examples:
            T[M] = self.tensor[:,M,...]
            T[M,N] = self.tensor[:,M,:,N]
            T[:,N] = self.tensor[:,:,:,N]
            T[[1,2,3],:] = self.tensor[:,[1,2,3],:,N]
            T[[1,2,3],[4,5]] = self.tensor[:,[1,2,3],:,[4,5]]  # i.e. the rows [1,2,3] and columns [4,5]
        """

        _all = slice(None)
        if isinstance(item, int):
            return XPTensor.from_tensor(backend.expand_dims(self.tensor[:,item,...], axis=1), modes=(self.modes[0][item], self.modes[1]), like_0=self.like_0)
        if self.tensor is None:
            return XPTensor(like_0=self.like_0)
        if isinstance(item, tuple) and len(item) == 2:
            if self.isVector:
                raise ValueError("Cannot index a vector with 2 indices")
        # the right indices (don't exceed 2 or 1 index)



    def __setitem__(self, key, value: XPTensor):
        if self.isMatrix:
            self._tensor = backend.setitem(self.tensor, (slice(), key[0], slice(), key[1]), value.tensor[:, key[0], :, key[1]])
        else:
            self._tensor = backend.setitem(self.tensor, (slice(), key), value.tensor[:, key])

    def __getitem_tuple(self, item=None):
        if isinstance(item, int):
            lst = [item]
        elif isinstance(item, slice):
            lst = list(range(item.start or 0, item.stop or self.nmodes, item.step))
        elif isinstance(item, List):
            lst = np.array(item)
        elif item is None:
            lst = slice(None)
        else:
            raise ValueError(f"Invalid item: {item}")
        return lst


