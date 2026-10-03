import type { components } from './schema'

// Names for the generated API types (schema.d.ts comes from /openapi.json: `npm run gen:api`).
type S = components['schemas']

export type Recommendation = S['RecommendationItemOut']
export type RecommendationResponse = S['RecommendationResponseOut']
export type RatingIn = S['RatingIn']
export type RatingAccepted = S['RatingAccepted']
export type RatingStatus = S['RatingStatus']
export type RatedMovie = S['RatedMovieOut']
export type RatingHistory = S['RatingHistoryOut']
export type DebugUser = S['DebugUserOut']
export type SystemStatus = S['SystemStatusOut']
export type ModelVersion = S['ModelVersionOut']
export type GateCheck = S['GateCheckOut']
export type DemoMovie = S['DemoMovieOut']
export type MovieCreated = S['MovieCreated']
export type RetrainProgress = S['RetrainProgressOut']
export type Popularity = S['PopularityOut']
export type MovieList = S['MovieListOut']
export type MovieRow = S['MovieRowOut']
export type PopularityItem = S['PopularityItemOut']
