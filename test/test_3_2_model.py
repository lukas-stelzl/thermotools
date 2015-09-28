# This file is part of thermotools.
#
# Copyright 2015 Computational Molecular Biology Group, Freie Universitaet Berlin (GER)
#
# thermotools is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import thermotools.wham as wham
import thermotools.tram as tram
import thermotools.dtram as dtram
import numpy as np
from numpy.testing import assert_allclose

#   ************************************************************************************************
#   fixed-point iterations
#   ************************************************************************************************

def run_dtram(C_K_ij, b_K_i, maxiter, ftol):
    log_nu_K_i = np.zeros(shape=b_K_i.shape, dtype=np.float64)
    f_i = np.zeros(shape=b_K_i.shape[1], dtype=np.float64)
    f_K_i = b_K_i.copy()
    dtram.set_lognu(log_nu_K_i, C_K_ij)
    scratch_TM = np.zeros(shape=b_K_i.shape, dtype=np.float64)
    scratch_M = np.zeros(shape=f_i.shape, dtype=np.float64)
    old_f_K_i = np.zeros(shape=f_K_i.shape, dtype=np.float64)
    old_log_nu_K_i = log_nu_K_i.copy()
    old_f_i = f_i.copy()
    for m in range(maxiter):
        dtram.iterate_lognu(old_log_nu_K_i, b_K_i, f_i, C_K_ij, scratch_M, log_nu_K_i)
        dtram.iterate_fi(log_nu_K_i, b_K_i, old_f_i, C_K_ij, scratch_TM, scratch_M, f_i)
        f_K_i = f_i[np.newaxis, :] + b_K_i
        if np.max(np.abs(f_K_i - old_f_K_i)) < ftol:
            break
        else:
            old_f_i[:] = f_i[:]
            old_f_K_i[:] = f_K_i[:]
            old_log_nu_K_i[:] = log_nu_K_i[:]
    f_K = dtram.get_fk(b_K_i, f_i, scratch_M)
    P_K_ij = dtram.get_pk(log_nu_K_i, b_K_i, f_i, C_K_ij, scratch_M)
    return f_K, f_i, f_K_i, P_K_ij

def run_tram(C_K_ij, N_K_i, b_K_x, M_x, maxiter, ftol):
    log_nu_K_i = np.zeros(shape=N_K_i.shape, dtype=np.float64)
    f_K_i = np.zeros(shape=N_K_i.shape, dtype=np.float64)
    log_R_K_i = np.zeros(shape=N_K_i.shape, dtype=np.float64)
    scratch_T = np.zeros(shape=(C_K_ij.shape[0],), dtype=np.float64)
    scratch_M = np.zeros(shape=(C_K_ij.shape[1],), dtype=np.float64)
    tram.set_lognu(log_nu_K_i, C_K_ij)
    old_f_K_i = f_K_i.copy()
    old_log_nu_K_i = log_nu_K_i.copy()
    for m in range(maxiter):
        tram.iterate_lognu(old_log_nu_K_i, f_K_i, C_K_ij, scratch_M, log_nu_K_i)
        tram.iterate_fki(log_nu_K_i, old_f_K_i, C_K_ij, b_K_x, M_x,
            N_K_i, log_R_K_i, scratch_M, scratch_T, f_K_i)
        if np.max(np.abs(f_K_i - old_f_K_i)) < ftol:
            break
        else:
            old_f_K_i[:] = f_K_i[:]
            old_log_nu_K_i[:] = log_nu_K_i[:]
    f_i = tram.get_fi(b_K_x, M_x, log_R_K_i, scratch_M, scratch_T)
    tram.normalize_fki(f_i, f_K_i, scratch_M)
    P_K_ij = tram.get_pk(log_nu_K_i, f_K_i, C_K_ij, scratch_M)
    return f_K_i, f_i, P_K_ij


#   ************************************************************************************************
#   data generation functions
#   ************************************************************************************************

def tower_sample(distribution):
    cdf = np.cumsum(distribution)
    rnd = np.random.rand() * cdf[-1]
    ind = (cdf > rnd)
    idx = np.where(ind == True)
    return np.min(idx)

def draw_independent_samples(pi_K_i, n_samples):
    N_K_i = np.zeros(shape=pi_K_i.shape, dtype=np.intc)
    for K in range(pi_K_i.shape[0]):
        for s in range(n_samples):
            N_K_i[K, tower_sample(pi_K_i[K, :])] += 1
    return N_K_i

def draw_transition_counts(P_K_ij, n_samples, x0):
    """generates a discrete Markov chain"""
    C_K_ij = np.zeros(P_K_ij.shape, dtype=np.intc)
    M_x = np.zeros(P_K_ij.shape[0]*(n_samples+1), dtype=np.intc)
    N_K_i = np.zeros(shape=P_K_ij.shape[0:2], dtype=np.intc)
    h = 0
    for K in range(P_K_ij.shape[0]):
        x = x0
        N_K_i[K, x] += 1
        M_x[h] = x
        h += 1
        for s in range(n_samples):
            x_new = tower_sample(P_K_ij[K, x, :])
            C_K_ij[K, x, x_new] += 1
            x = x_new
            N_K_i[K, x] += 1
            M_x[h] = x
            h += 1
    return C_K_ij, M_x, N_K_i

#   ************************************************************************************************
#   test class
#   ************************************************************************************************

class TestThreeTwoModel(object):
    @classmethod
    def setup_class(cls):
        cls.energy = np.array([1.0, 2.0, 0.0], dtype=np.float64)
        cls.b_K_i = np.array([[0.0, 0.0, 0.0], 2.0 - cls.energy], dtype=np.float64)
        cls.pi_i = np.exp(-cls.energy) / np.exp(-cls.energy).sum()
        cls.f_i = -np.log(cls.pi_i)
        cls.f_K_i = cls.f_i[np.newaxis, :] + cls.b_K_i
        cls.Z_K_i = np.exp(-cls.f_K_i)
        cls.Z_K = cls.Z_K_i.sum(axis=1)
        cls.f_K = -np.log(cls.Z_K)
        cls.pi_K_i = np.exp(-cls.b_K_i) * cls.pi_i[np.newaxis, :] / cls.Z_K[:, np.newaxis]
        metropolis = cls.energy[np.newaxis, :] - cls.energy[:, np.newaxis]
        metropolis[(metropolis < 0.0)] = 0.0
        selection = np.array([[0.5, 0.5, 0.0], [0.5, 0.0, 0.5], [0.0, 0.5, 0.5]], dtype=np.float64)
        metr_hast = selection * np.exp(-metropolis)
        for i in range(metr_hast.shape[0]):
            metr_hast[i, i] = 0.0
            metr_hast[i, i] = 1.0 - metr_hast[i, :].sum()
        cls.P_K_ij = np.array([metr_hast, selection])
        cls.n_samples = 10000
        cls.N_K_i = draw_independent_samples(cls.pi_K_i, cls.n_samples)
        cls.C_K_ij,cls.M_x,cls.N_K_i_TRAM = draw_transition_counts(cls.P_K_ij, cls.n_samples, 0)
    @classmethod
    def teardown_class(cls):
        pass
    def setup(self):
        pass
    def teardown(self):
        pass
    def test_wham(self):
        f_K, f_i = wham.estimate(self.N_K_i, self.b_K_i, maxiter=50000, maxerr=1.0E-15)
        atol = 1.0E-1
        assert_allclose(f_K, self.f_K, atol=atol)
        assert_allclose(f_i, self.f_i, atol=atol)
    def test_dtram(self):
        f_K, f_i, f_K_i, P_K_ij = run_dtram(self.C_K_ij, self.b_K_i, 10000, 1.0E-15)
        maxerr = 1.0E-1
        assert_allclose(f_K, self.f_K, atol=maxerr)
        assert_allclose(f_i, self.f_i, atol=maxerr)
        assert_allclose(f_K_i, self.f_K_i, atol=maxerr)
        assert_allclose(P_K_ij, self.P_K_ij, atol=maxerr)
    def test_tram(self):
        b_K_x = np.ascontiguousarray(self.b_K_i[:,self.M_x])
        f_K_i, f_i, P_K_ij = run_tram(self.C_K_ij, self.N_K_i_TRAM, b_K_x, self.M_x, 10000, 1.0E-15)
        maxerr = 1.0E-1
        assert_allclose(f_K_i, self.f_K_i, atol=maxerr)
        assert_allclose(f_i, self.f_i, atol=maxerr)
        assert_allclose(P_K_ij, self.P_K_ij, atol=maxerr)

