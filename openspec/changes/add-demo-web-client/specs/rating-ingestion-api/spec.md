## ADDED Requirements

### Requirement: Submit a rating over HTTP
The API SHALL expose `POST /ratings` accepting a JSON body with `userId`, `movieId`, `rating` and an optional `eventId`, and SHALL publish an event conforming to CONTRACTS.md §5 to Kafka topic `ratings.v1` with the record key set to `userId`.

#### Scenario: Valid rating accepted
- **WHEN** a client posts `{userId: 500001, movieId: 296, rating: 4.0}`
- **THEN** the API returns HTTP 202 with the `eventId` that was published, and the event is readable from `ratings.v1` with key `"500001"`

#### Scenario: Server-assigned timestamp
- **WHEN** a rating is accepted
- **THEN** the published event's `timestamp` is the server's receive time in epoch seconds, regardless of any timestamp the client sends

### Requirement: 202 means durably accepted, not applied
The API SHALL return 202 only after Kafka has acknowledged the record with `acks=all`; it MUST NOT wait for the streaming pipeline to apply the event, and SHALL return HTTP 503 with a reason when Kafka does not acknowledge within the configured timeout.

#### Scenario: Kafka unavailable
- **WHEN** a client posts a valid rating while the Kafka broker is unreachable
- **THEN** the API returns HTTP 503 with a reason, and no 202 is returned

#### Scenario: Reads unaffected by Kafka outage
- **WHEN** the Kafka broker is unreachable
- **THEN** `GET /recommendations/{userId}` continues to return HTTP 200 from MongoDB

### Requirement: API-side validation before publishing
The API SHALL reject with HTTP 422, without publishing to Kafka, any request whose `userId` is not a positive integer, whose `rating` is not in {0.5, 1.0, …, 5.0}, whose `movieId` does not exist in the `movies` collection, or whose supplied `eventId` is empty or longer than 64 characters. The streaming pipeline's own validation MUST remain in place unchanged, because other producers may publish to the topic without going through the API.

#### Scenario: Invalid rating value
- **WHEN** a client posts `{userId: 1, movieId: 296, rating: 7.0}`
- **THEN** the API returns HTTP 422 and nothing is published to Kafka

#### Scenario: Unknown movie
- **WHEN** a client posts a `movieId` that is not in `movies`
- **THEN** the API returns HTTP 422 naming the unknown movie and nothing is published

### Requirement: Client-supplied idempotency key
The API SHALL use a client-supplied `eventId` as the published event's `eventId` and SHALL generate a UUID4 when none is supplied, so a client retrying the same logical rating with the same `eventId` is applied at most once by the pipeline.

#### Scenario: Same eventId posted twice
- **WHEN** a client posts the same rating twice with the same `eventId`
- **THEN** both requests return 202 with that `eventId`, and after the pipeline processes them the `rating_events` ledger holds exactly one document for that `eventId`

### Requirement: Rating status lookup
The API SHALL expose `GET /ratings/{eventId}` returning `{status: "applied", batchId, ingestedAt}` when the `rating_events` ledger contains that `eventId`, and `{status: "pending"}` otherwise.

#### Scenario: Pending then applied
- **WHEN** a client posts a valid rating and immediately queries its status while the streaming pipeline is running
- **THEN** the status is `pending` at first and becomes `applied` after the pipeline's next micro-batch commits

#### Scenario: Pipeline stopped
- **WHEN** the streaming pipeline is not running and a client posts a valid rating
- **THEN** the status stays `pending`, and becomes `applied` after the pipeline is restarted and catches up from its checkpoint
