/**
 * Document download/verify URLs are constructed inline by the components that need them
 * (so the browser handles streaming + Content-Disposition). Payment helpers historically
 * lived here; they have moved to ``./payments``. This file is kept as a back-compat
 * re-export so external imports keep working while we transition.
 */
export { calculateFees, processPayment } from './payments';
export type { FeeBreakdown } from './payments';
