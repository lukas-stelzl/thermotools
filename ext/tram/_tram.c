/*
* This file is part of thermotools.
*
* Copyright 2015 Computational Molecular Biology Group, Freie Universitaet Berlin (GER)
*
* thermotools is free software: you can redistribute it and/or modify
* it under the terms of the GNU Lesser General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU Lesser General Public License
* along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include <math.h>
#include "../lse/_lse.h"
#include "_tram.h"

/* old m$ visual studio is not c99 compliant (vs2010 eg. is not) */
#ifdef _MSC_VER
    #include <float.h>
    #define INFINITY (DBL_MAX+DBL_MAX)
    #define NAN (INFINITY-INFINITY)
#endif

void _set_lognu(double *log_nu_K_i, int *C_K_ij, int n_therm_states, int n_markov_states)
{
    int i, j, K;
    int MM = n_markov_states * n_markov_states, KMM;
    int sum;
    for(K=0; K<n_therm_states; ++K)
    {
        KMM = K * MM;
        for(i=0; i<n_markov_states; ++i)
        {
            sum = 0;
            for(j=0; j<n_markov_states; ++j)
                sum += C_K_ij[KMM + i * n_markov_states + j];
            log_nu_K_i[K * n_markov_states + i] = log(THERMOTOOLS_TRAM_PRIOR + sum);
        }
    }

}

void _iterate_lognu(
    double *log_nu_K_i, double *f_K_i, int *C_K_ij,
    int n_therm_states, int n_markov_states, double *scratch_M, double *new_log_nu_K_i)
{
    int i, j, K, o;
    int MM = n_markov_states * n_markov_states, Ki, Kj, KM, KMM;
    int CK, CKij;
    double divisor;
    for(K=0; K<n_therm_states; ++K)
    {
        KM = K * n_markov_states;
        KMM = KM * n_markov_states;
        for(i=0; i<n_markov_states; ++i)
        {
            Ki = KM + i;
            o = 0;
            for(j=0; j<n_markov_states; ++j)
            {
                CKij = C_K_ij[KMM + i * n_markov_states + j];
                /* special case: most variables cancel out, here */
                if(i == j)
                {
                    scratch_M[o++] = (0 == CKij) ?
                        THERMOTOOLS_TRAM_LOG_PRIOR : log(THERMOTOOLS_TRAM_PRIOR + (double) CKij);
                    continue;
                }
                CK = CKij + C_K_ij[KMM + j * n_markov_states + i];
                /* special case */
                if(0 == CK) continue;
                /* regular case */
                Kj = KM + j;
                divisor = _logsumexp_pair(log_nu_K_i[Kj] - f_K_i[Ki], log_nu_K_i[Ki] - f_K_i[Kj]);
                scratch_M[o++] = log((double) CK) + log_nu_K_i[Ki] - f_K_i[Kj] - divisor;
            }
            new_log_nu_K_i[Ki] = _logsumexp(scratch_M, o);
        }
    }
}

void _iterate_fki(
    double *log_nu_K_i, double *f_K_i, int *C_K_ij, double *b_K_x,
    int *M_x, int *N_K_i, int seq_length, double *log_R_K_i,
    int n_therm_states, int n_markov_states, double *scratch_M, double *scratch_T,
    double *new_f_K_i, int K_target)
{
    int i, j, K, I, l, x, o;
    int MM = n_markov_states * n_markov_states, Ki, Kj, KM, KMM;
    int Ci, CK, CKij, CKji, NC;
    double divisor, R_addon, norm;
    /* compute R_K_i */
    for(K=0; K<n_therm_states; ++K)
    {
        KM = K * n_markov_states;
        KMM = KM * n_markov_states;
        for(i=0; i<n_markov_states; ++i)
        {
            Ci = 0;
            Ki = KM + i;
            o = 0;
            for(j=0; j<n_markov_states; ++j)
            {
                CKij = C_K_ij[KMM + i * n_markov_states + j];
                CKji = C_K_ij[KMM + j * n_markov_states + i];
                Ci += CKji;
                /* special case: most variables cancel out, here */
                if(i == j)
                {
                    scratch_M[o] = (0 == CKij) ? THERMOTOOLS_TRAM_LOG_PRIOR : log(THERMOTOOLS_TRAM_PRIOR + (double) CKij);
                    scratch_M[o++] += f_K_i[Ki];
                    continue;
                }
                CK = CKij + CKji;
                /* special case */
                if(0 == CK) continue;
                /* regular case */
                Kj = KM + j;
                divisor = _logsumexp_pair(log_nu_K_i[Kj] - f_K_i[Ki], log_nu_K_i[Ki] - f_K_i[Kj]);
                scratch_M[o++] = log((double) CK) + log_nu_K_i[Kj] - divisor;
            }
            NC = N_K_i[Ki] - Ci;
            R_addon = (0 < NC) ? log((double) NC) + f_K_i[Ki] : -INFINITY; /* IGNORE PRIOR */
            log_R_K_i[Ki] = _logsumexp_pair(_logsumexp(scratch_M, o), R_addon);
        }
    }
    /* set new_f_K_i to infinity (z_K_i==0) */
    for(K=0; K<n_therm_states; ++K)
    {
        for(i=0; i<n_markov_states; ++i)
            new_f_K_i[K * n_markov_states + i] = INFINITY;
    }
    /* compute new f_K_i */
    for( x=0; x<seq_length; ++x )
    {
        i = M_x[x];
        for(K=0; K<n_therm_states; ++K)
            scratch_T[K] = log_R_K_i[K * n_markov_states + i] - b_K_x[K * seq_length + x];
        divisor = _logsumexp(scratch_T, n_therm_states);
        for(K=0; K<n_therm_states; ++K)
        {
            new_f_K_i[K * n_markov_states + i] = -_logsumexp_pair(
                    -new_f_K_i[K * n_markov_states + i], -(divisor + b_K_x[K * seq_length + x]));
        }
    }
    /* apply normalization */
    for(i=0; i<n_markov_states; ++i)
        scratch_M[i] = -new_f_K_i[K_target * n_markov_states + i];
    norm = _logsumexp(scratch_M, n_markov_states);
    for(K=0; K<n_therm_states; ++K)
    {
        for(i=0; i<n_markov_states; ++i)
            new_f_K_i[K * n_markov_states + i] += norm;
    }
}

void _f_ground_state(
    double *b_K_x, int *M_x, int seq_length, double *log_R_K_i,
    int n_therm_states, int n_markov_states, double *scratch_M, double *scratch_T,
    double *f_ground_i)
{
    int i, K, x;
    double divisor, norm;

    /* set f_ground_i to infinity (pi_i==0) */
    for(i=0; i<n_markov_states; ++i)
        f_ground_i[i] = INFINITY;
    
    /* compute new f_ground_i */
    for( x=0; x<seq_length; ++x )
    {
        i = M_x[x];
        for(K=0; K<n_therm_states; ++K)
            scratch_T[K] = log_R_K_i[K * n_markov_states + i] - b_K_x[K * seq_length + x];
        divisor = _logsumexp(scratch_T, n_therm_states);
        f_ground_i[i] = -_logsumexp_pair(-f_ground_i[i], -divisor);
    }
    /* apply normalization */
    for(i=0; i<n_markov_states; ++i)
        scratch_M[i] = -f_ground_i[i];
    norm = _logsumexp(scratch_M, n_markov_states);
    for(i=0; i<n_markov_states; ++i)
        f_ground_i[i] += norm;
}