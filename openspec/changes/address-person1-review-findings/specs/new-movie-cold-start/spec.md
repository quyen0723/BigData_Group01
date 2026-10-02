## ADDED Requirements

### Requirement: Placed new movies keep scores non-increasing
When new movies are placed into the response, every placed item SHALL take the score of the item it displaces first (or the last item's score when placing at the end), so the `score` values of the response remain in non-increasing order for any value of `new_items.slots`.

#### Scenario: Two slots in the middle of the list
- **WHEN** the fused list scores are [0.9, 0.8, 0.7] and two new movies are placed starting at rank 2
- **THEN** the response scores are [0.9, 0.8, 0.8, 0.8, 0.7] cut to `k`, and no score is greater than the one before it

#### Scenario: Placement at the end
- **WHEN** the position is beyond the last item
- **THEN** the placed items take the last item's score and the order stays non-increasing

#### Scenario: One slot unchanged
- **WHEN** `new_items.slots` is 1
- **THEN** the response is identical to the behaviour before this change
