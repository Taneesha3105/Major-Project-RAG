import { useOutletContext } from "react-router-dom";

/** Shared state for every tab of the deal workspace: { deal, reloadDeal, can }. */
export function useDeal() {
  return useOutletContext();
}
