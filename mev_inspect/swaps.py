from itertools import groupby
from typing import List, Optional

from mev_inspect.schemas.classified_traces import (
    ClassifiedTrace,
    Classification,
)
from mev_inspect.schemas.swaps import Swap
from mev_inspect.schemas.transfers import Transfer
from mev_inspect.transfers import (
    get_child_transfers,
    filter_transfers,
    remove_inner_transfers,
)


UNISWAP_V2_PAIR_ABI_NAME = "UniswapV2Pair"
UNISWAP_V3_POOL_ABI_NAME = "UniswapV3Pool"


def get_swaps(traces: List[ClassifiedTrace]) -> List[Swap]:
    get_transaction_hash = lambda t: t.transaction_hash
    traces_by_transaction = groupby(
        sorted(traces, key=get_transaction_hash),
        key=get_transaction_hash,
    )

    swaps = []

    for _, transaction_traces in traces_by_transaction:
        swaps += _get_swaps_for_transaction(list(transaction_traces))

    return swaps


def _get_swaps_for_transaction(traces: List[ClassifiedTrace]) -> List[Swap]:
    ordered_traces = list(sorted(traces, key=lambda t: t.trace_address))

    swaps: List[Swap] = []
    prior_transfers: List[Transfer] = []

    for trace in ordered_traces:
        if trace.classification == Classification.transfer:
            prior_transfers.append(Transfer.from_trace(trace))

        elif trace.classification == Classification.swap:
            child_transfers = get_child_transfers(
                trace.transaction_hash,
                trace.trace_address,
                traces,
            )

            swap = _parse_swap(
                trace,
                remove_inner_transfers(prior_transfers),
                remove_inner_transfers(child_transfers),
            )

            if swap is not None:
                swaps.append(swap)

    return swaps


def _parse_swap(
    trace: ClassifiedTrace,
    prior_transfers: List[Transfer],
    child_transfers: List[Transfer],
) -> Optional[Swap]:
    pool_address = trace.to_address
    recipient_address = _get_recipient_address(trace)

    if recipient_address is None:
        return None

    transfers_to_pool = filter_transfers(prior_transfers, to_address=pool_address)

    if len(transfers_to_pool) == 0:
        transfers_to_pool = filter_transfers(child_transfers, to_address=pool_address)

    if len(transfers_to_pool) == 0:
        return None

    transfers_from_pool_to_recipient = filter_transfers(
        child_transfers, to_address=recipient_address, from_address=pool_address
    )

    if len(transfers_from_pool_to_recipient) != 1:
        return None

    transfer_in = transfers_to_pool[-1]
    transfer_out = transfers_from_pool_to_recipient[0]

    return Swap(
        abi_name=trace.abi_name,
        transaction_hash=trace.transaction_hash,
        block_number=trace.block_number,
        trace_address=trace.trace_address,
        pool_address=pool_address,
        from_address=transfer_in.from_address,
        to_address=transfer_out.to_address,
        token_in_address=transfer_in.token_address,
        token_in_amount=transfer_in.amount,
        token_out_address=transfer_out.token_address,
        token_out_amount=transfer_out.amount,
    )


def _get_recipient_address(trace: ClassifiedTrace) -> Optional[str]:
    if trace.abi_name == UNISWAP_V3_POOL_ABI_NAME:
        return (
            trace.inputs["recipient"]
            if trace.inputs is not None and "recipient" in trace.inputs
            else trace.from_address
        )
    elif trace.abi_name == UNISWAP_V2_PAIR_ABI_NAME:
        return (
            trace.inputs["to"]
            if trace.inputs is not None and "to" in trace.inputs
            else trace.from_address
        )
    else:
        return None
