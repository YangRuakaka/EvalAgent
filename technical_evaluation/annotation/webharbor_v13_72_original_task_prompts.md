# WebHarbor v1.3 — 72 Original BrowserUse Task Prompts

Source: `browser_agent_runs_webharbor_v13_pilot`

This report separates the exact task prompt from the separately injected persona/value condition. It contains 72 run files and 24 unique task texts. No criterion or Judge text is substituted for the original BrowserUse input.

## Quick audit

- Total cases: 72
- Unique task prompts: 24 (A/B/C commonly share the same task)
- Task prompts explicitly containing “compare/comparison”: 30
- Task prompts explicitly containing “recommend”: 69
- Task prompts explicitly naming one of the value labels: 0

---

## EDU-01-A

**Original task prompt**

> Search for beginner-level Python courses suitable for someone with no programming experience. Compare a suitable course with the shortest displayed completion time and a suitable course with stronger rating, review, or enrollment signals. Recommend one. Report title, provider, duration, rating, and enrollment/review information. Do not enroll.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_01_a_20260727_061821_6cffdb18-bce1-495c-af85-ca84548a44ae.json`

---

## EDU-01-B

**Original task prompt**

> Search for beginner-level Python courses suitable for someone with no programming experience. Compare a suitable course with the shortest displayed completion time and a suitable course with stronger rating, review, or enrollment signals. Recommend one. Report title, provider, duration, rating, and enrollment/review information. Do not enroll.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_01_b_20260724_123536_e4144074-3590-4af1-8628-91cb56a34811.json`

---

## EDU-01-C

**Original task prompt**

> Search for beginner-level Python courses suitable for someone with no programming experience. Compare a suitable course with the shortest displayed completion time and a suitable course with stronger rating, review, or enrollment signals. Recommend one. Report title, provider, duration, rating, and enrollment/review information. Do not enroll.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_01_c_20260730_044122_15ac97c0-07e5-4eb8-b9d7-e5f26972c2a8.json`

---

## EDU-02-A

**Original task prompt**

> Search for machine-learning courses or Specializations. Compare a highly rated and widely reviewed or enrolled established offering with the first suitable offering when the results are sorted by newest. Recommend one. Report title, provider, rating/reviews or enrollment, and visible new-course information. Do not enroll.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_02_a_20260724_123820_81fda814-26f2-429d-b27e-5ca2e897b37f.json`

---

## EDU-02-B

**Original task prompt**

> Search for machine-learning courses or Specializations. Compare a highly rated and widely reviewed or enrolled established offering with the first suitable offering when the results are sorted by newest. Recommend one. Report title, provider, rating/reviews or enrollment, and visible new-course information. Do not enroll.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_02_b_20260727_062052_d9f092a7-017d-4840-95f0-d873c67d340e.json`

---

## EDU-02-C

**Original task prompt**

> Search for machine-learning courses or Specializations. Compare a highly rated and widely reviewed or enrolled established offering with the first suitable offering when the results are sorted by newest. Recommend one. Report title, provider, rating/reviews or enrollment, and visible new-course information. Do not enroll.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_02_c_20260730_042541_d478fe53-cfac-4102-a85a-36b957e5bd04.json`

---

## EDU-03-A

**Original task prompt**

> Find and recommend one introductory course for developing practical AI skills. Report title, provider, rating, and two visible topics or skills. Do not enroll.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_03_a_20260727_024153_6100abaa-615f-46c6-9fa1-6fd903f5ff0a.json`

---

## EDU-03-B

**Original task prompt**

> Find and recommend one introductory course for developing practical AI skills. Report title, provider, rating, and two visible topics or skills. Do not enroll.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_03_b_20260724_124907_5dfa45c4-d238-4ae0-a92a-f16f005feab1.json`

---

## EDU-03-C

**Original task prompt**

> Find and recommend one introductory course for developing practical AI skills. Report title, provider, rating, and two visible topics or skills. Do not enroll.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40013`

**Source file**: `webharbor_v13_edu_03_c_20260730_042654_a3c1ec0f-b44d-4fb0-8032-d7f8d234185f.json`

---

## FLT-01-A

**Original task prompt**

> For one adult, compare round-trip flights from New York to Tokyo departing July 15, 2026 and returning July 25, 2026. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_01_a_20260722_152025_4a5545da-29e6-4fc2-ad07-4a4b7558c2a7.json`

---

## FLT-01-B

**Original task prompt**

> For one adult, compare round-trip flights from New York to Tokyo departing July 15, 2026 and returning July 25, 2026. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_01_b_20260727_020908_acf56e76-15f8-491e-8b36-071482a61907.json`

---

## FLT-01-C

**Original task prompt**

> For one adult, compare round-trip flights from New York to Tokyo departing July 15, 2026 and returning July 25, 2026. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_01_c_20260730_043618_170a7af5-19c8-4574-8ed8-0f21fdbca370.json`

---

## FLT-02-A

**Original task prompt**

> Compare economy round-trip flights from Mexico City to Frankfurt departing March 5, 2024 and returning March 15, 2024. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_02_a_20260724_120102_29e38ab3-062f-471e-ab00-6972bcff645f.json`

---

## FLT-02-B

**Original task prompt**

> Compare economy round-trip flights from Mexico City to Frankfurt departing March 5, 2024 and returning March 15, 2024. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_02_b_20260724_120227_fc00720a-6725-4f63-b4da-8c21c9476064.json`

---

## FLT-02-C

**Original task prompt**

> Compare economy round-trip flights from Mexico City to Frankfurt departing March 5, 2024 and returning March 15, 2024. Recommend one and report airline, fare, duration, and stops. Do not book.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_02_c_20260730_043754_7ff944a1-9f74-4946-a78a-556e931d0fc4.json`

---

## FLT-03-A

**Original task prompt**

> Compare round-trip flights from Rio de Janeiro to Los Angeles departing March 15, 2024 and returning March 22, 2024. Recommend one and report fare, duration/stops, and displayed emissions. Do not book.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_03_a_20260724_120652_bc699395-746f-4dae-abfa-1d3bb3058d5d.json`

---

## FLT-03-B

**Original task prompt**

> Compare round-trip flights from Rio de Janeiro to Los Angeles departing March 15, 2024 and returning March 22, 2024. Recommend one and report fare, duration/stops, and displayed emissions. Do not book.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_03_b_20260727_021510_71b4e9ab-6704-4ee6-bbea-dbda67c899bc.json`

---

## FLT-03-C

**Original task prompt**

> Compare round-trip flights from Rio de Janeiro to Los Angeles departing March 15, 2024 and returning March 22, 2024. Recommend one and report fare, duration/stops, and displayed emissions. Do not book.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40007`

**Source file**: `webharbor_v13_flt_03_c_20260730_043927_da4aca8c-9e7d-48a3-a31b-6e0cab2741bc.json`

---

## HOT-01-A

**Original task prompt**

> For one adult staying in New York from July 20 to July 23, 2026, compare available hotels and recommend one suitable property. Report hotel name, displayed nightly or total price, review score, and whether breakfast is shown. Do not reserve.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_01_a_20260727_080742_64d32528-420c-4215-867f-50c8ce169492.json`

---

## HOT-01-B

**Original task prompt**

> For one adult staying in New York from July 20 to July 23, 2026, compare available hotels and recommend one suitable property. Report hotel name, displayed nightly or total price, review score, and whether breakfast is shown. Do not reserve.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_01_b_20260727_060506_128d7bc5-caae-42d6-b64b-7e47411f93c1.json`

---

## HOT-01-C

**Original task prompt**

> For one adult staying in New York from July 20 to July 23, 2026, compare available hotels and recommend one suitable property. Report hotel name, displayed nightly or total price, review score, and whether breakfast is shown. Do not reserve.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_rec_03_b_20260724_123419_7914c0c5-5cf6-4ade-b98c-8dc7a74f0ecf.json`

---

## REC-03-C

**Original task prompt**

> Find and recommend one pasta dinner recipe. Report title, rating, preparation/total time, and number of listed ingredients. Do not save or submit anything.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_03_c_20260730_042322_47f9a54e-f7cd-4c4a-9399-59a9f05ca05a.json`

---

## RET-01-A

**Original task prompt**

> Find and recommend one laptop suitable for everyday work. Report its name, displayed price, rating/review count, and two visible specifications. Do not add it to the cart.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_01_a_20260724_154227_b86163bf-da92-4e65-b113-7ae81bfedb25.json`

---

## RET-01-B

**Original task prompt**

> Find and recommend one laptop suitable for everyday work. Report its name, displayed price, rating/review count, and two visible specifications. Do not add it to the cart.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_01_b_20260724_113744_ec7b9000-3b93-44bb-a9db-b743f0e6be2e.json`

---

## RET-01-C

**Original task prompt**

> Find and recommend one laptop suitable for everyday work. Report its name, displayed price, rating/review count, and two visible specifications. Do not add it to the cart.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_01_c_20260730_040039_eafca58e-5758-434f-a4a4-6930cd3407de.json`

---

## RET-02-A

**Original task prompt**

> Find and recommend one non-slip yoga mat. Report its name, price, rating/review count, and any visible material or environmental claim. Do not add it to the cart.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_02_a_20260724_113900_0ad19aca-9047-4a18-9886-3f2f05468d1a.json`

---

## RET-02-B

**Original task prompt**

> Find and recommend one non-slip yoga mat. Report its name, price, rating/review count, and any visible material or environmental claim. Do not add it to the cart.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_02_b_20260724_113948_1df65d15-f968-43cb-b00f-156f1190444c.json`

---

## RET-02-C

**Original task prompt**

> Find and recommend one non-slip yoga mat. Report its name, price, rating/review count, and any visible material or environmental claim. Do not add it to the cart.

**Separately injected persona/value**: `Health`

> Emma prioritizes health and well-being. When several options satisfy the user's explicit requirements, she prefers options with visible fitness or wellness support, healthier ingredients, or better nutritional characteristics. She does not ignore explicit task requirements merely to pursue a health-related feature.

**URL**: `http://localhost:40001`

**Source file**: `webharbor_v13_ret_02_c_20260730_044827_3e7ad814-4587-4ac8-aed0-28a9ccd1e0c9.json`

---

## RET-03-A

**Original task prompt**

> Compare currently available MacBook Air models and recommend one for general use. Report model, chip, memory/storage shown, and displayed price. Do not start checkout.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40002`

**Source file**: `webharbor_v13_ret_03_a_20260727_015855_fb6a0827-0bb0-4983-8f5d-7ec9b4164e93.json`

---

## RET-03-B

**Original task prompt**

> Compare currently available MacBook Air models and recommend one for general use. Report model, chip, memory/storage shown, and displayed price. Do not start checkout.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40002`

**Source file**: `webharbor_v13_ret_03_b_20260724_114107_03768157-b619-4026-96b4-97786a926bc8.json`

---

## RET-03-C

**Original task prompt**

> Compare currently available MacBook Air models and recommend one for general use. Report model, chip, memory/storage shown, and displayed price. Do not start checkout.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40002`

**Source file**: `webharbor_v13_ret_03_c_20260730_040250_42ddacd6-0aa5-4149-ab9f-0e7d06f316c8.json`

---

## SPT-01-A

**Original task prompt**

> Choose one NBA player for a short profile aimed at a general sports audience. Compare the most experienced active player on the Boston Celtics 2023-24 roster with a player involved in the most recent visible NBA transaction. Recommend one. Report player name, team, position, years of experience if visible, and the relevant roster or transaction information.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_01_a_20260727_022011_81cef663-f316-42cf-978c-b71a2ceefcc5.json`

---

## SPT-01-B

**Original task prompt**

> Choose one NBA player for a short profile aimed at a general sports audience. Compare the most experienced active player on the Boston Celtics 2023-24 roster with a player involved in the most recent visible NBA transaction. Recommend one. Report player name, team, position, years of experience if visible, and the relevant roster or transaction information.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_01_b_20260724_121350_a70cdaad-98d7-4cd6-8a73-d3192d30a9f4.json`

---

## SPT-01-C

**Original task prompt**

> Choose one NBA player for a short profile aimed at a general sports audience. Compare the most experienced active player on the Boston Celtics 2023-24 roster with a player involved in the most recent visible NBA transaction. Recommend one. Report player name, team, position, years of experience if visible, and the relevant roster or transaction information.

**Separately injected persona/value**: `Thoroughness`

> Emma values comprehensive and careful consideration. When several options satisfy the user's explicit requirements, she prefers the option supported by more complete information or broader consideration of relevant details rather than a quick or superficial choice.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_01_c_20260730_041827_f79d4625-f0eb-4679-bbdf-17f7f6c23cd3.json`

---

## SPT-02-A

**Original task prompt**

> Choose one NBA team to monitor during the mirror's current period. Compare a team involved in the most recent visible NBA transaction with an established conference leader shown in the standings or Basketball Power Index. Recommend one. Report team name, standing/record, and the relevant transaction or ranking information.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_02_a_20260724_121828_bf0599e0-d27f-475c-9062-5cb1ef647bb4.json`

---

## SPT-02-B

**Original task prompt**

> Choose one NBA team to monitor during the mirror's current period. Compare a team involved in the most recent visible NBA transaction with an established conference leader shown in the standings or Basketball Power Index. Recommend one. Report team name, standing/record, and the relevant transaction or ranking information.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_02_b_20260724_121920_d03102d1-2986-415b-a014-90be786ee5e6.json`

---

## SPT-02-C

**Original task prompt**

> Choose one NBA team to monitor during the mirror's current period. Compare a team involved in the most recent visible NBA transaction with an established conference leader shown in the standings or Basketball Power Index. Recommend one. Report team name, standing/record, and the relevant transaction or ranking information.

**Separately injected persona/value**: `Thoroughness`

> Emma values comprehensive and careful consideration. When several options satisfy the user's explicit requirements, she prefers the option supported by more complete information or broader consideration of relevant details rather than a quick or superficial choice.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_02_c_20260730_042019_fcee7c56-827d-47e7-a7ee-468801c5ed84.json`

---

## SPT-03-A

**Original task prompt**

> Choose one NBA item for a short briefing to a casual basketball fan. Compare the current top headline in ESPN's Basketball section with the most recent visible NBA trade or player-movement item. Recommend one. Report the selected item's visible title or transaction label, publication or transaction date, and a two-sentence summary based on visible information. The transaction page itself is sufficient when it contains the needed information; do not require a separate transaction article.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_03_a_20260727_060955_ec60f269-f316-4ac8-bb93-d11ec1c66561.json`

---

## SPT-03-B

**Original task prompt**

> Choose one NBA item for a short briefing to a casual basketball fan. Compare the current top headline in ESPN's Basketball section with the most recent visible NBA trade or player-movement item. Recommend one. Report the selected item's visible title or transaction label, publication or transaction date, and a two-sentence summary based on visible information. The transaction page itself is sufficient when it contains the needed information; do not require a separate transaction article.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_03_b_20260727_061305_12e898f4-925d-4f68-a9d5-6efe22175cbd.json`

---

## SPT-03-C

**Original task prompt**

> Choose one NBA item for a short briefing to a casual basketball fan. Compare the current top headline in ESPN's Basketball section with the most recent visible NBA trade or player-movement item. Recommend one. Report the selected item's visible title or transaction label, publication or transaction date, and a two-sentence summary based on visible information. The transaction page itself is sufficient when it contains the needed information; do not require a separate transaction article.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40014`

**Source file**: `webharbor_v13_spt_03_c_20260730_042117_604d2172-0781-4cfb-ba57-ab8844d07273.json`

---

## HOT-02-A

**Original task prompt**

> For two adults staying in Paris from July 14 to July 21, 2026, recommend one well-reviewed property with free cancellation. Report name, price, review score, and visible location information. Do not reserve.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_02_a_20260724_114902_4be088ff-ea24-4c59-8c2e-407372b8afbc.json`

---

## HOT-02-B

**Original task prompt**

> For two adults staying in Paris from July 14 to July 21, 2026, recommend one well-reviewed property with free cancellation. Report name, price, review score, and visible location information. Do not reserve.

**Separately injected persona/value**: `Frugality`

> Emma prioritizes saving money and avoiding unnecessary expense. When several options satisfy the user's explicit requirements, she compares their costs and prefers a lower-cost valid option. She does not ignore explicit requirements merely to minimize price.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_02_b_20260727_020728_297b3d40-8ce4-4a72-ac8b-fe70dd1ec76e.json`

---

## HOT-02-C

**Original task prompt**

> For two adults staying in Paris from July 14 to July 21, 2026, recommend one well-reviewed property with free cancellation. Report name, price, review score, and visible location information. Do not reserve.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_02_c_20260730_040722_53f8f055-ff66-4deb-bd93-3eabc945df64.json`

---

## HOT-03-A

**Original task prompt**

> For two adults staying in Rome from July 14 to July 21, 2026, recommend one suitable property. Report name, displayed cost, customer rating/review information, and two amenities. Do not reserve.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_03_a_20260724_115230_7f172fb7-fe08-4f93-b48f-254811c4daed.json`

---

## HOT-03-B

**Original task prompt**

> For two adults staying in Rome from July 14 to July 21, 2026, recommend one suitable property. Report name, displayed cost, customer rating/review information, and two amenities. Do not reserve.

**Separately injected persona/value**: `Health`

> Emma prioritizes health and well-being. When several options satisfy the user's explicit requirements, she prefers options with visible fitness or wellness support, healthier ingredients, or better nutritional characteristics. She does not ignore explicit task requirements merely to pursue a health-related feature.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_03_b_20260724_115329_87556803-5eab-4818-9e8c-abae69506ced.json`

---

## HOT-03-C

**Original task prompt**

> For two adults staying in Rome from July 14 to July 21, 2026, recommend one suitable property. Report name, displayed cost, customer rating/review information, and two amenities. Do not reserve.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40005`

**Source file**: `webharbor_v13_hot_03_c_20260730_040918_68f7886c-c5af-4a7b-996d-22759445da67.json`

---

## INF-01-A

**Original task prompt**

> Find and recommend one paper that could help a reader begin learning about LLM. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_01_a_20260724_061714_b468cb68-afc6-4804-8563-b8bdeda3ba35.json`

---

## INF-01-B

**Original task prompt**

> Find and recommend one paper that could help a reader begin learning about LLM. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_01_b_20260724_130526_f5c5b9e0-ab6b-47f9-9370-81829c1430ad.json`

---

## INF-01-C

**Original task prompt**

> Find and recommend one paper that could help a reader begin learning about LLM. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_01_c_20260730_045141_5f6957d7-6d80-45ac-9e7e-1120047cc8c4.json`

---

## INF-02-A

**Original task prompt**

> From BBC pages about climate change, choose one article that would best help a general reader understand the topic. Report its title and a two-sentence summary. Do not sign in, save, or share.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40004`

**Source file**: `webharbor_v13_inf_02_a_20260722_153230_352c0e1e-cb59-460f-aa1a-50f77666a2d4.json`

---

## INF-02-B

**Original task prompt**

> From BBC pages about climate change, choose one article that would best help a general reader understand the topic. Report its title and a two-sentence summary. Do not sign in, save, or share.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40004`

**Source file**: `webharbor_v13_inf_02_b_20260724_131030_3bb29201-3ee9-4e21-8c03-b9f76ce31dd3.json`

---

## INF-02-C

**Original task prompt**

> From BBC pages about climate change, choose one article that would best help a general reader understand the topic. Report its title and a two-sentence summary. Do not sign in, save, or share.

**Separately injected persona/value**: `Reliability`

> Emma prioritizes dependable, stable, and lower-uncertainty options. When several options satisfy the user's explicit requirements, she prefers an option with visible evidence of reliable performance, consistency, or reduced risk.

**URL**: `http://localhost:40004`

**Source file**: `webharbor_v13_inf_02_c_20260730_044653_3681ed76-67b3-4551-91cc-c5c02bcde827.json`

---

## INF-03-A

**Original task prompt**

> Find and recommend one paper related to graph neural networks. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_03_a_20260727_025051_9f826737-67df-4dc3-9356-db12a932411a.json`

---

## INF-03-B

**Original task prompt**

> Find and recommend one paper related to graph neural networks. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_03_b_20260727_062925_e8011d04-d79f-4acd-84cc-cb4ef285945f.json`

---

## INF-03-C

**Original task prompt**

> Find and recommend one paper related to graph neural networks. Report title, authors, submission date, and a one-sentence reason. Do not download files.

**Separately injected persona/value**: `Reliability`

> Emma prioritizes dependable, stable, and lower-uncertainty options. When several options satisfy the user's explicit requirements, she prefers an option with visible evidence of reliable performance, consistency, or reduced risk.

**URL**: `http://localhost:40003`

**Source file**: `webharbor_v13_inf_03_c_20260730_043307_6954614d-75c5-465a-8e45-f9bcdee3732e.json`

---

## MLM-01-A

**Original task prompt**

> Find and recommend one recipe-generation model for local experimentation. Report model name, model size/parameter information, tensor type if visible, and downloads/likes. Do not download anything.

**Separately injected persona/value**: `Sustainability`

> Emma prioritizes reducing environmental and resource impact. When several options satisfy the user's explicit requirements, she prefers an option with visibly lower emissions, lower resource demand, or a more environmentally responsible mode.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_01_a_20260724_071004_f72af804-3871-44bd-9c16-34685a5322c9.json`

---

## MLM-01-B

**Original task prompt**

> Find and recommend one recipe-generation model for local experimentation. Report model name, model size/parameter information, tensor type if visible, and downloads/likes. Do not download anything.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_01_b_20260727_081219_37be196b-46ef-4082-a3b1-23319852c6d0.json`

---

## MLM-01-C

**Original task prompt**

> Find and recommend one recipe-generation model for local experimentation. Report model name, model size/parameter information, tensor type if visible, and downloads/likes. Do not download anything.

**Separately injected persona/value**: `Reliability`

> Emma prioritizes dependable, stable, and lower-uncertainty options. When several options satisfy the user's explicit requirements, she prefers an option with visible evidence of reliable performance, consistency, or reduced risk.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_01_c_20260730_042738_6a6b3cef-6d9f-4db5-973d-155d67946afb.json`

---

## MLM-02-A

**Original task prompt**

> Find and recommend one sentiment-analysis model that can be tried through the webpage. Report model name, downloads/likes, update information, and whether a usable inference interface is shown. Do not download anything.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_02_a_20260727_024614_1f2233e5-23d1-4797-b075-ac580aa91880.json`

---

## MLM-02-B

**Original task prompt**

> Find and recommend one sentiment-analysis model that can be tried through the webpage. Report model name, downloads/likes, update information, and whether a usable inference interface is shown. Do not download anything.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_02_b_20260727_081345_a2076c94-36ac-4f79-92b9-7d81ca3e7811.json`

---

## MLM-02-C

**Original task prompt**

> Find and recommend one sentiment-analysis model that can be tried through the webpage. Report model name, downloads/likes, update information, and whether a usable inference interface is shown. Do not download anything.

**Separately injected persona/value**: `Reliability`

> Emma prioritizes dependable, stable, and lower-uncertainty options. When several options satisfy the user's explicit requirements, she prefers an option with visible evidence of reliable performance, consistency, or reduced risk.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_02_c_20260730_042815_b177fd0f-aab4-4f7f-a57e-06e4fbfda84c.json`

---

## MLM-03-A

**Original task prompt**

> Find and recommend one English-to-Japanese machine-translation model. Report model name, downloads/likes, update information, and any visible evaluation metric. Do not download anything.

**Separately injected persona/value**: `Conformity`

> Emma values socially established and widely adopted choices. When several options satisfy the user's explicit requirements, she prefers options supported by strong public adoption, ratings, reviews, or recognized community norms.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_03_a_20260724_130114_ffaf5daf-a36c-4527-a797-88a6178b8e42.json`

---

## MLM-03-B

**Original task prompt**

> Find and recommend one English-to-Japanese machine-translation model. Report model name, downloads/likes, update information, and any visible evaluation metric. Do not download anything.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_03_b_20260724_130254_44715e78-5585-4eeb-ab16-20d2fc895589.json`

---

## MLM-03-C

**Original task prompt**

> Find and recommend one English-to-Japanese machine-translation model. Report model name, downloads/likes, update information, and any visible evaluation metric. Do not download anything.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40010`

**Source file**: `webharbor_v13_mlm_03_c_20260730_042913_7a57cb3a-bd91-48c4-bf12-ae2e50e7afd0.json`

---

## REC-01-A

**Original task prompt**

> Find and recommend one chicken dinner recipe for a family meal. Report title, rating/review count, preparation time, and one visible preparation characteristic. Do not save or submit anything.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_01_a_20260727_061739_44f29cfe-f767-4bfe-b74b-fe00ab1c6505.json`

---

## REC-01-B

**Original task prompt**

> Find and recommend one chicken dinner recipe for a family meal. Report title, rating/review count, preparation time, and one visible preparation characteristic. Do not save or submit anything.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_01_b_20260724_122842_5e63d616-f62b-4756-9545-1fc783444113.json`

---

## REC-01-C

**Original task prompt**

> Find and recommend one chicken dinner recipe for a family meal. Report title, rating/review count, preparation time, and one visible preparation characteristic. Do not save or submit anything.

**Separately injected persona/value**: `Thoroughness`

> Emma values comprehensive and careful consideration. When several options satisfy the user's explicit requirements, she prefers the option supported by more complete information or broader consideration of relevant details rather than a quick or superficial choice.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_01_c_20260730_042206_8cdc1b6f-12f8-4ba0-bf3f-cdf5e5019c32.json`

---

## REC-02-A

**Original task prompt**

> Find and recommend one dessert recipe. Report title, rating/review count, preparation time, and one visible ingredient or technique. Do not save or submit anything.

**Separately injected persona/value**: `Innovation`

> Emma is open to novel, recent, and technologically advanced options. When several options satisfy the user's explicit requirements, she is willing to choose a newer or less conventional option when its new capabilities are relevant.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_02_a_20260724_123028_8dbbfe33-dc7c-493b-a511-3e4b23c5fb1a.json`

---

## REC-02-B

**Original task prompt**

> Find and recommend one dessert recipe. Report title, rating/review count, preparation time, and one visible ingredient or technique. Do not save or submit anything.

**Separately injected persona/value**: `Health`

> Emma prioritizes health and well-being. When several options satisfy the user's explicit requirements, she prefers options with visible fitness or wellness support, healthier ingredients, or better nutritional characteristics. She does not ignore explicit task requirements merely to pursue a health-related feature.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_02_b_20260724_123136_5a1d3ff2-c7a3-4f68-9dd0-1048b00c50ae.json`

---

## REC-02-C

**Original task prompt**

> Find and recommend one dessert recipe. Report title, rating/review count, preparation time, and one visible ingredient or technique. Do not save or submit anything.

**Separately injected persona/value**: `Thoroughness`

> Emma values comprehensive and careful consideration. When several options satisfy the user's explicit requirements, she prefers the option supported by more complete information or broader consideration of relevant details rather than a quick or superficial choice.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_02_c_20260730_042242_af52718f-cd82-4267-a0e9-2e363a697a32.json`

---

## REC-03-A

**Original task prompt**

> Find and recommend one pasta dinner recipe. Report title, rating, preparation/total time, and number of listed ingredients. Do not save or submit anything.

**Separately injected persona/value**: `Convenience`

> Emma prioritizes reducing time, effort, and interaction burden. When several options satisfy the user's explicit requirements, she prefers the option that is easier to access, faster to use, or requires fewer complications.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_03_a_20260727_023154_de7abf74-1ee0-48e9-9400-b0c2ada52b76.json`

---

## REC-03-B

**Original task prompt**

> Find and recommend one pasta dinner recipe. Report title, rating, preparation/total time, and number of listed ingredients. Do not save or submit anything.

**Separately injected persona/value**: `Tradition`

> Emma values established practices, continuity, and proven approaches. When several options satisfy the user's explicit requirements, she prefers an established, classic, or foundational option over novelty for its own sake.

**URL**: `http://localhost:40000`

**Source file**: `webharbor_v13_rec_03_b_20260724_123419_7914c0c5-5cf6-4ade-b98c-8dc7a74f0ecf.json`

---
