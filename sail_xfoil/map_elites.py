"""
Perform MAP-Elites iterations.

Candidate solutions are generated by a custom emitter class, which
adds Gaussian Noise scaled to the boundaries of solution space.

These samples are then evaluated on their respective objective
function. In the case of SAIL, MAP-Elites is used to optimize
acquisition & prediction values as objective.
"""

from ribs.emitters._emitter_base import EmitterBase
from ribs.emitters import GaussianEmitter
from ribs.archives import GridArchive
from ribs.schedulers import Scheduler
from tqdm import tqdm
import numpy as np

from gp.predict_objective import predict_objective

from config.config import Config
import numpy as np
config = Config('config/config.ini')
BATCH_SIZE = config.BATCH_SIZE
SIGMA_EMITTER = config.SIGMA_EMITTER
SIGMA_MUTANTS = config.SIGMA_MUTANTS
SOL_DIMENSION = config.SOL_DIMENSION
SOL_VALUE_RANGE = config.SOL_VALUE_RANGE
OBJ_BHV_NUMBER_BINS = config.OBJ_BHV_NUMBER_BINS
ACQ_BHV_NUMBER_BINS = config.ACQ_BHV_NUMBER_BINS
BHV_VALUE_RANGE = config.BHV_VALUE_RANGE
ACQ_N_MAP_EVALS = config.ACQ_N_MAP_EVALS
PRED_N_MAP_EVALS = config.PRED_N_MAP_EVALS
PREDICTION_VERIFICATIONS = config.PREDICTION_VERIFICATIONS

def map_elites(self, acq_flag=False, pred_flag=False, new_elite_archive=None):

    print("\n\nInitialize Map-Elites [...]")

    if self.acq_mes_flag and acq_flag:
        # Update Cellgrids using a new seed
        self.update_mutant_cellgrids()

    if new_elite_archive is None:
        # new_elite_archive is a code relict, but kept for compatibility
        number_bins = ACQ_BHV_NUMBER_BINS if acq_flag else OBJ_BHV_NUMBER_BINS

        new_elite_archive = GridArchive(
            solution_dim=SOL_DIMENSION,
            dims=number_bins,
            ranges=BHV_VALUE_RANGE,)


    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
    self.acq_archive.clear()

    if self.custom_flag:
        # Update Archive with existing acquisition/prediction elites
        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=acq_flag, pred_flag=pred_flag,
                            niche_restricted_update=True, sigma_mutants=0.2)
        if self.acq_mes_flag and acq_flag:
            acq_sum_t0 = np.sum(self.acq_archive.as_pandas().objective_batch())
            print(f"Acquisition Value Sum (before update): {acq_sum_t0:.3f}")

    if self.acq_ucb_flag:
        obj_elite_df = self.obj_archive.as_pandas(include_solutions=True)
        self.update_archive(candidate_sol=obj_elite_df.solution_batch(), candidate_bhv=obj_elite_df.measures_batch(), acq_flag=acq_flag, pred_flag=pred_flag)

    if self.acq_mes_flag and acq_flag:
        acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                            niche_restricted_update = True, sigma_mutants=0.2)
        self.visualize_archive(archive=self.acq_archive, map_flag=True)

        acq_sum_t1 = np.sum(self.acq_archive.as_pandas().objective_batch())
        print(f"Acquisition Value Sum (after update): {acq_sum_t1:.3f}")

    mes_flag = self.acq_mes_flag and acq_flag
    if acq_flag:
        target_function = self.acq_function
        target_archive = self.acq_archive
        n_evals = ACQ_N_MAP_EVALS if mes_flag else ACQ_N_MAP_EVALS*20

    if pred_flag:
        target_function = predict_objective
        target_archive = self.pred_archive
        n_evals = PRED_N_MAP_EVALS if not self.pred_verific_flag else PRED_N_MAP_EVALS//(PREDICTION_VERIFICATIONS+1)

    remaining_evals = n_evals
    total_iterations = remaining_evals // BATCH_SIZE

    with tqdm(total=total_iterations) as progress:
        while((remaining_evals-BATCH_SIZE >= 0)):

            progress.update(1)

            sigma_mutants = SIGMA_MUTANTS + 0.2*(remaining_evals/n_evals)
            sigma_emitter = SIGMA_EMITTER + 0.2*(remaining_evals/n_evals)
            emitter = update_emitter(self, target_archive=target_archive, sigma_emitter=sigma_emitter, mes_flag=mes_flag)

            scheduler = _Scheduler(target_archive, emitter)

            genome_batch = scheduler.ask()

            # Calculate Acquisitions/Predictions
            candidate_sol = genome_batch
            candidate_bhv = genome_batch[:,1:3]
            candidate_obj = target_function(self=self, genomes=candidate_sol, sigma_mutants=sigma_mutants, niche_restricted_update=True)

            if mes_flag and acq_flag:
                candidate_sol = self.mes_elites

            target_archive.add(solution_batch=candidate_sol, objective_batch=candidate_obj, measures_batch=candidate_bhv)


            if mes_flag:

                if remaining_evals % (n_evals//8) == 0 and remaining_evals != n_evals and remaining_evals != BATCH_SIZE:

                    if remaining_evals % (n_evals//2) == 0 and remaining_evals != n_evals and remaining_evals != BATCH_SIZE:
                        acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                        print(f"t-1: {np.sum(acq_elite_df.objective_batch()):.3f}")
                        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                                            niche_restricted_update=True, sigma_mutants=0.1)

                    self.visualize_archive(archive=self.acq_archive, map_flag=True)
                    print("updating...")

                    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                    print(f"t0: {np.sum(acq_elite_df.objective_batch()):.3f}")
                    self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                                        niche_restricted_update=True, sigma_mutants=0.5)

                    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                    print(f"t1: {np.sum(acq_elite_df.objective_batch()):.3f}")
                    self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                                        niche_restricted_update=True, sigma_mutants=0.3 + 0.1*(remaining_evals/n_evals))

                    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                    t0_acq_elite_df = acq_elite_df.copy()
                    print(f"t2: {np.sum(acq_elite_df.objective_batch()):.3f}")
                    self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                                        niche_restricted_update=True, sigma_mutants=0.3)

                    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                    print(f"t3: {np.sum(acq_elite_df.objective_batch()):.3f}")
                    self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                                        niche_restricted_update=True, sigma_mutants=0.15 + 0.15*(remaining_evals/n_evals))

                    acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
                    print(f"t4: {np.sum(acq_elite_df.objective_batch()):.3f}")

                    self.visualize_archive(archive=self.acq_archive, map_flag=True)


            remaining_evals -= BATCH_SIZE

    # Niche Restricted Mutant Update
    if mes_flag:

        acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
        print(f"Before Update: {np.sum(acq_elite_df.objective_batch()):.3f}")

        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                            niche_restricted_update=True, sigma_mutants=0.5)
        acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
        print(f"First Update: {np.sum(self.acq_archive.as_pandas().objective_batch()):.3f}")

        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                            niche_restricted_update=True, sigma_mutants=0.2)
        acq_elite_df = self.acq_archive.as_pandas(include_solutions=True)
        print(f"Second Update: {np.sum(self.acq_archive.as_pandas().objective_batch()):.3f}")

        self.update_archive(candidate_sol=acq_elite_df.solution_batch(), candidate_bhv=acq_elite_df.measures_batch(), acq_flag=True,
                            niche_restricted_update=True, sigma_mutants=0.1)
        print(f"Final Update: {np.sum(self.acq_archive.as_pandas().objective_batch()):.3f}")

        self.visualize_archive(archive=self.acq_archive, map_flag=True)

    print("[...] End Map-Elites\n\n")

    # new_elite_archive is a code relict, but kept for compatibility
    new_elite_archive = target_archive
    return new_elite_archive


def update_emitter(self, target_archive, sigma_emitter=SIGMA_EMITTER, sol_value_range=SOL_VALUE_RANGE, mes_flag=None):

    self.update_seed()

    emitter = [
        _Gaussian_LocalCompetitionEmitter(
        archive=target_archive,
        sigma=sigma_emitter,
        bounds= np.array(sol_value_range),
        batch_size=BATCH_SIZE,
        seed=self.current_seed,
        mes_flag=mes_flag
    )]

    return emitter


class _Gaussian_LocalCompetitionEmitter(GaussianEmitter):

    """
    Custom Emitter class

    - Scales Gaussian Noise to the boundaries of the solution space

    """

    def __init__(self,
                 archive,
                 *,
                 sigma,
                 bounds=None,
                 batch_size=BATCH_SIZE,
                 seed=None,
                 mes_flag=False):

        self._rng = np.random.default_rng(seed)
        self._batch_size = batch_size
        self._sigma = np.array(sigma, dtype=archive.dtype)
        self.mes_flag = mes_flag

        if archive.stats.num_elites == 0:
            raise ValueError("Archive must be filled with initial solutions.")

        EmitterBase.__init__(
            self,
            archive,
            solution_dim=archive.solution_dim,
            bounds=bounds,
        )

    @property
    def sigma(self):
        """float or numpy.ndarray: Standard deviation of the (diagonal) Gaussian
        distribution when the archive is not empty."""
        return self._sigma

    @property
    def batch_size(self):
        """int: Number of solutions to return in :meth:`ask`."""
        return self._batch_size

    def mes_local_competition(self):

        mes_elite_df = self.archive.as_pandas(include_solutions=True)

        df_indices = mes_elite_df['index'].values
        archive_dims = self.archive.dims
        row_dim = archive_dims[0]

        for index in df_indices:

            neighbor_index_up = index+row_dim
            neighbor_index_down = index-row_dim

            neighbor_indices = []
            neighbor_indices.append(neighbor_index_up) if neighbor_index_up < np.prod(archive_dims)-1 else None
            neighbor_indices.append(neighbor_index_down) if neighbor_index_down >= 0 else None

            if index%row_dim != 0:
                neighbor_index_left = index-1
                neighbor_index_left_up = index-1+row_dim
                neighbor_index_left_down = index-1-row_dim
                neighbor_indices.append(neighbor_index_left) if neighbor_index_left >= 0 else None
                neighbor_indices.append(neighbor_index_left_up) if neighbor_index_left_up < np.prod(archive_dims)-1 else None
                neighbor_indices.append(neighbor_index_left_down) if neighbor_index_left_down >= 0 else None
            if (index+1) % row_dim != 0:
                neighbor_index_right = index+1
                neighbor_index_right_up = index+1+row_dim
                neighbor_index_right_down = index-1-row_dim
                neighbor_indices.append(neighbor_index_right) if neighbor_index_right < np.prod(archive_dims)-1 else None
                neighbor_indices.append(neighbor_index_right_up) if neighbor_index_right_up < np.prod(archive_dims)-1 else None
                neighbor_indices.append(neighbor_index_right_down) if neighbor_index_right_down >= 0 else None

            elite = mes_elite_df[mes_elite_df['index'] == index]
            elite_neighbors = mes_elite_df[mes_elite_df['index'].isin(neighbor_indices)]
            mean_relative_improvement = np.mean(elite['objective'].values / elite_neighbors['objective'].values)
            mes_elite_df.loc[mes_elite_df['index'] == index, 'mean_relative_improvement'] = mean_relative_improvement

        # Preserve 65% of highestperforming local elites
        n_elites = max(self._batch_size, int(mes_elite_df.shape[0]*0.65))
        mes_elite_df = mes_elite_df.sort_values(by='mean_relative_improvement', ascending=False)
        mes_elite_df = mes_elite_df.head(self.batch_size)
        mes_elite_df = mes_elite_df.head(n_elites)
        mes_elite_df = mes_elite_df.sample(n=self._batch_size, random_state=self._rng, replace=False)

        mes_parents = mes_elite_df.solution_batch()
        return mes_parents

    def ask(self):
        """Creates solutions by adding Gaussian noise to elites in the archive.

        Each solution is drawn from a distribution centered at a randomly
        chosen elite with standard deviation ``self.sigma``.
        """

        if not self.mes_flag:
            parents = self.archive.sample_elites(self._batch_size).solution_batch
        else:
            parents = self.mes_local_competition()

        scaled_noise = self._rng.normal(
            scale=np.abs(self._sigma*(self.upper_bounds-self.lower_bounds)),
            size=(self._batch_size, self.solution_dim),
        )

        return np.clip(parents + scaled_noise, self.lower_bounds, self.upper_bounds)


class _Scheduler(Scheduler):
    """
    Overwwrite Scheduler removing error messages
    This allows for more freedom by not requiring
    to use scheduler.ask() scheduler.tell() as
    required by the original implementation.
    """

    def ask(self):

        self._last_called = "ask"
        self._solution_batch = []

        for i, emitter in enumerate(self._emitters):
            emitter_sols = emitter.ask()
            self._solution_batch.append(emitter_sols)
            self._num_emitted[i] = len(emitter_sols)

        # In case the emitters didn't return any solutions.
        self._solution_batch = np.concatenate(
            self._solution_batch, axis=0) if self._solution_batch else np.empty(
                (0, self._solution_dim))
        return self._solution_batch


    def _check_length(self, name, array):
        """Raises a ValueError if array does not have the same length as the
        solutions."""
        if len(array) != len(self._solution_batch):
            raise ValueError(
                f"{name} should have length {len(self._solution_batch)} "
                "(this is the number of solutions output by ask()) but "
                f"has length {len(array)}")

    EMPTY_WARNING = (
        "`{name}` was empty before adding solutions, and it is still empty "
        "after adding solutions. "
        "One potential cause is that `threshold_min` is too high in this "
        "archive, i.e., solutions are not being inserted because their "
        "objective value does not exceed `threshold_min`.")
