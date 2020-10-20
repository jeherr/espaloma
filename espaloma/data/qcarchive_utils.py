# =============================================================================
# IMPORTS
# =============================================================================
from typing import Tuple

import numpy as np
import qcportal as ptl
import torch
from simtk import unit
from simtk.unit.quantity import Quantity

import espaloma as esp


# =============================================================================
# CONSTANTS
# =============================================================================


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def get_client():
    return ptl.FractalClient()


def get_collection(
        client,
        collection_type="OptimizationDataset",
        name="OpenFF Full Optimization Benchmark 1",
):
    collection = client.get_collection(
        collection_type,
        name,
    )

    record_names = list(collection.data.records)

    return collection, record_names


def get_graph(collection, record_name):
    # get record and trajectory
    record = collection.get_record(record_name, specification="default")
    entry = collection.get_entry(record_name)
    from openforcefield.topology import Molecule
    mol = Molecule.from_qcschema(entry)

    try:
        trajectory = record.get_trajectory()
    except:
        return None

    if trajectory is None:
        return None

    g = esp.Graph(mol)

    # energy is already hartree
    g.nodes['g'].data['u_ref'] = torch.tensor(
        [
            Quantity(
                snapshot.properties.scf_total_energy,
                esp.units.HARTREE_PER_PARTICLE
            ).value_in_unit(
                esp.units.ENERGY_UNIT
            )
            for snapshot in trajectory
        ],
        dtype=torch.get_default_dtype(),
    )[None, :]

    g.nodes['n1'].data['xyz'] = torch.tensor(
        np.stack(
            [
                Quantity(
                    snapshot.get_molecule().geometry,
                    unit.bohr,
                ).value_in_unit(
                    esp.units.DISTANCE_UNIT
                )
                for snapshot in trajectory
            ],
            axis=1
        ),
        requires_grad=True,
        dtype=torch.get_default_dtype(),
    )

    g.nodes['n1'].data['u_ref_prime'] = torch.stack(
        [
            torch.tensor(
                Quantity(
                    snapshot.dict()['return_result'],
                    esp.units.HARTREE_PER_PARTICLE / unit.bohr,
                ).value_in_unit(
                    esp.units.FORCE_UNIT
                ),
                dtype=torch.get_default_dtype(),
            )
            for snapshot in trajectory
        ],
        dim=1
    )

    return g


def get_energy_and_gradient(snapshot: ptl.models.records.ResultRecord) -> Tuple[float, np.ndarray]:
    """Note: force = - gradient"""
    d = snapshot.dict()
    qcvars = d['extras']['qcvars']
    energy = qcvars['CURRENT ENERGY']
    flat_gradient = np.array(qcvars['CURRENT GRADIENT'])
    num_atoms = len(flat_gradient) // 3
    gradient = flat_gradient.reshape((num_atoms, 3))
    return energy, gradient
