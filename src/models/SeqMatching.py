import os
import argparse
import pickle
import time

import numpy as np
from tqdm import trange, tqdm

from src import utils, geometry
from src.params import descriptors


class SeqMatching:
    def __init__(
        self,
        map_poses,
        map_descriptors,
        wContrast,
        numVel,
        vMin,
        vMax,
        matchWindow,
        enhance=False,
    ):
        self.map_poses = map_poses
        self.map_descriptors = map_descriptors
        self.wContrast = wContrast
        self.numVel = numVel
        self.vMin = vMin
        self.vMax = vMax
        self.matchWindow = matchWindow
        self.enhance = enhance

    def localize(self, query_descriptors):
        D = self._compute_diff_matrix(query_descriptors)
        if self.enhance:
            D = self._enhance_contrast(D)
        template_scores = self._score_ref_templates(D)
        ind, score = self._locate_best_match(template_scores)
        proposal = self.map_poses[ind]
        return proposal, score

    def _compute_diff_matrix(self, query_descriptors):
        # generate descriptor difference matrix
        D = np.sqrt(2 - 2 * np.dot(self.map_descriptors, query_descriptors.transpose()))
        return D

    def _enhance_contrast(self, D):
        nref = D.shape[0]
        Denhanced = np.empty_like(D)
        for i in range(nref):
            # reference indices of window around each reference image
            idx_lower = max(i - int(self.wContrast / 2), 0)
            idx_upper = min(i + int(self.wContrast / 2) + 1, nref - 1)
            # local normalization of window given by indices above
            Denhanced[i, :] = (
                D[i, :] - np.mean(D[idx_lower:idx_upper, :], axis=0)
            ) / np.std(D[idx_lower:idx_upper, :], axis=0)
        return Denhanced

    def _score_ref_templates(self, D):
        N = D.shape[0]
        L = D.shape[1]

        velocities = np.linspace(self.vMin, self.vMax, self.numVel + 1)
        times = np.arange(L)  # t = 0, ..., L
        # i = 0, ..., max_ind <- truncated so line search not cut off
        max_ind = int(N - 1 - self.vMax * L)
        # last template image to begin sequence matching on
        refs = np.arange(max_ind)
        # D score for best velocity for each starting
        # point (template image)
        optD = np.empty(max_ind)
        optD[:] = np.inf
        for vel in velocities:
            # indices in D for line search given a particular velocity
            row_indices = (
                np.floor(refs[:, np.newaxis] + vel * times[np.newaxis, :])
                .astype(int)
                .reshape(-1)
            )
            col_indices = np.tile(times, max_ind)
            # evaluate D at indices and sum to get aggregate difference
            Dsum = np.sum(D[row_indices, col_indices].reshape(max_ind, L), axis=1)
            # for sequence matching scores better than
            # prior scores (under different velocities), update
            ind_better = Dsum < optD
            optD[ind_better] = Dsum[ind_better]
        return optD

    def _locate_best_match(self, template_scores):
        # indices of best match and window around it
        iOpt = np.argmin(template_scores)
        iWinL = np.maximum(iOpt - int(self.matchWindow / 2), 0)
        iWinU = np.minimum(iOpt + int(self.matchWindow / 2), len(template_scores))
        # check best match outside window
        outside_scores = np.concatenate(
            (template_scores[:iWinL], template_scores[iWinU:])
        )
        optOutside = min(outside_scores)
        # for negative scores, u \in [0, 1]
        # increases the score... adjust
        if optOutside > 0:
            mu = template_scores[iOpt] / optOutside
        else:
            mu = optOutside / template_scores[iOpt]
        return iOpt, mu


def main(args):
    # load reference data
    ref_poses, ref_descriptors, _ = utils.import_reference_map(args.reference_traverse)
    # localize all selected query traverses
    pbar = tqdm(args.query_traverses)
    for traverse in pbar:
        pbar.set_description(traverse)
        # savepath
        save_path = os.path.join(utils.results_path, traverse)
        # load query data
        query_poses, _, _, query_descriptors, _ = utils.import_query_traverse(traverse)
        # regular traverse with VO
        pbar = tqdm(args.descriptors, leave=False)
        for desc in pbar:
            pbar.set_description(desc)
            # one folder per descriptor
            save_path1 = os.path.join(save_path, desc)
            if not os.path.exists(save_path1):
                os.makedirs(save_path1)
            model = SeqMatching(
                ref_poses,
                ref_descriptors[desc],
                args.wContrast,
                args.numVel,
                args.vMin,
                args.vMax,
                args.matchWindow,
                args.enhance,
            )
            proposals, scores, times, query_gt = utils.localize_traverses_matching(
                model,
                query_poses,
                query_descriptors[desc][:, : args.seq_len, :],
                desc="Seq Match",
            )
            utils.save_obj(
                save_path1 + "/SeqMatch.pickle",
                model="Seq Match",
                query_gt=query_gt,
                proposals=proposals,
                scores=scores,
                times=times,
                L=args.seq_len,
            )
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run sequence matching on trials")
    parser.add_argument(
        "-r",
        "--reference-traverse",
        type=str,
        default="Overcast",
        help="reference traverse used as the map",
    )
    parser.add_argument(
        "-q",
        "--query-traverses",
        nargs="+",
        type=str,
        default=["Rain", "Dusk", "Night"],
        help=(
            "Names of query traverses to localize"
            "against reference map e.g. Overcast, Night,"
            "Dusk etc. Input 'all' instead to process all"
            "traverses. See src/params.py for full list."
        ),
    )
    parser.add_argument(
        "-d",
        "--descriptors",
        nargs="+",
        type=str,
        default=descriptors,
        help="descriptor types to run experiments on.",
    )
    parser.add_argument(
        "-L",
        "--seq-len",
        type=int,
        default=10,
        help="Sequence length for sequence matching",
    )
    parser.add_argument(
        "-wc",
        "--wContrast",
        type=int,
        default=10,
        help="window used for local contrast enhancementin difference matrix",
    )
    parser.add_argument(
        "-nv",
        "--numVel",
        type=int,
        default=20,
        help="number of velocities to search forsequence matching",
    )
    parser.add_argument(
        "-vm",
        "--vMin",
        type=float,
        default=1,
        help="minimum multiple of query to referencevelocity",
    )
    parser.add_argument(
        "-vM",
        "--vMax",
        type=float,
        default=10,
        help="maximum multiple of query to referencevelocity",
    )
    parser.add_argument(
        "-wm",
        "--matchWindow",
        type=int,
        default=20,
        help="window used for scoring optimaltrajectories for each reference",
    )
    parser.add_argument(
        "-e", "--enhance", action="store_true", help="apply contrast enhancement"
    )
    args = parser.parse_args()

    main(args)
