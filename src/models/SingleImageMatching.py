import os
import argparse
import pickle
import time

import numpy as np
from tqdm import trange, tqdm

from src import geometry, utils
from src.params import descriptors


class SingleImageMatching:
    def __init__(self, map_poses, map_descriptors):
        self.map_poses = map_poses
        self.map_descriptors = map_descriptors

    def localize(self, query_descriptors):
        return self.localize_descriptor(query_descriptors[0])

    def localize_descriptor(self, query_descriptor):
        dists = np.sqrt(2 - 2 * np.dot(self.map_descriptors, query_descriptor))
        idx = np.argmin(dists)
        proposal = self.map_poses[idx]
        score = dists[idx]
        return proposal, score


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
            model = SingleImageMatching(ref_poses, ref_descriptors[desc])
            proposals, scores, times, query_gt = utils.localize_traverses_matching(
                model, query_poses, query_descriptors[desc], desc="Single"
            )
            Trel = geometry.combine(proposals) / geometry.combine(query_gt)
            utils.save_obj(
                save_path1 + "/Single.pickle",
                model="Single",
                query_gt=query_gt,
                proposals=proposals,
                scores=scores,
                times=times,
            )
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single imagematching on trials")
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
    args = parser.parse_args()

    main(args)
