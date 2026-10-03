## ADDED Requirements

### Requirement: Admin movie catalog table
The admin section `#/movies` SHALL show, below the demo-movie panel, a "Danh mục phim" table fed by `GET /movies`, with a search field, a genre filter, a sort selector with a direction toggle, and pagination. Columns SHALL be the movie (title and genres), the number of ratings (with "+n mới" when new ratings exist), the average rating, the WR with four decimals, and a "demo" label for demo movies. A missing value SHALL show "—". The search SHALL be sent only after the user stops typing for 300 ms. The table SHALL show a loading placeholder, an error with a retry button, and "Không có phim nào khớp" when nothing matches, and SHALL show the total, the current page and the page count.

#### Scenario: Search
- **WHEN** the presenter types "pulp"
- **THEN** after the typing pauses the table lists movies whose title contains "pulp" and the total is shown

#### Scenario: Genre and sort
- **WHEN** the presenter selects the genre Western and sorts by number of ratings descending
- **THEN** the table shows only Western movies, the most rated first

#### Scenario: Pagination
- **WHEN** the presenter goes to the next page
- **THEN** the table shows the next movies and the page indicator advances; the previous page stays available

#### Scenario: Missing statistics
- **WHEN** a movie has ratings but no average
- **THEN** its average and WR cells show "—" and explain that statistics come from the training data

#### Scenario: Error
- **WHEN** the call fails
- **THEN** an error with a "Thử lại" button is shown and pressing it loads the table again

### Requirement: User page movie search
The user page SHALL have a "Tìm phim để chấm" section with a search field and a genre filter, above the recommendations. It SHALL call `GET /movies` only when the field holds at least two characters or a genre is selected, show 12 results at a time as movie cards with star ratings and a "Xem thêm" button, and SHALL NOT show technical words or statistics. Rating a result SHALL use the page's existing rating flow: the stars lock, the toasts appear, and when the rating is applied the recommendations and the rating history are refreshed. A movie found in the user's recent rating history SHALL show "Bạn đã chấm N sao" and remain ratable.

#### Scenario: Find and rate a movie
- **WHEN** a signed-in user types "pulp" and rates "Pulp Fiction" 5 stars
- **THEN** the stars lock with "Đang cập nhật gợi ý…", a saved toast appears, and when streaming has applied it the recommendations refresh and the movie shows "Bạn đã chấm 5 sao"

#### Scenario: Too short
- **WHEN** the field holds one character and no genre is selected
- **THEN** no request is sent and a hint asks for at least two characters

#### Scenario: Only a genre
- **WHEN** the user selects the genre Western with an empty field
- **THEN** Western movies are listed, the most rated first

#### Scenario: No result
- **WHEN** nothing matches
- **THEN** the section says "Không tìm thấy phim nào" and offers to clear the search

#### Scenario: Load more
- **WHEN** there are more than 12 results and the user presses "Xem thêm"
- **THEN** the next 12 are added below the first ones

#### Scenario: No technical words
- **WHEN** results are shown
- **THEN** the page contains no average rating, WR, tier or strategy text
