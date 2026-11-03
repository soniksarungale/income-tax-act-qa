# Sample questions and answers

Real outputs of the deployed app (https://taxqa.soniksarungale.com) on 3 November 2026, asked
through the chat page with provider `claude-cli` (claude-sonnet-5-5). Each was asked once; nothing
was re-run or edited. Answers vary slightly between runs because the CLI has no temperature setting.

These replace an earlier round of the same four questions, taken before the chat interface (commit
5c942e5). In that round the first question was partly answered: 4 of 5 points verified, because one
quote ("The provisions of sub-section (2) shall not apply if", the opening of section 23(3)) came from
the context line of the 23(3)(a) extract rather than its own text, which the verifier does not accept.

## 1. Rented house: 30% deduction and loan interest (the brief's example)

**Question:** I own a residential property that I have rented out. Can I claim a 30% deduction on the annual value of the property? I also have a housing loan on this property. Can I claim a deduction for the interest paid on the loan? Which sections of the Income-tax Act apply?

**Status:** answered. **Confidence:** high (0.88: verified 1.00, retrieval 0.86, agreement 1.00, completeness 0.50). **Time:** search 307 ms, answer 8.9 s.

1. Yes, Section 24(a) allows a deduction equal to thirty per cent of the annual value when computing income chargeable under the head "Income from house property". Your rented residential property falls under this head under Section 22.
   - Cited: Section 24 (Income-tax Act, 1961, PDF p. 92); Section 24(a) (Income-tax Act, 1961, PDF p. 92)
   - Quote: "a sum equal to thirty per cent of the annual value"
   - Verified: yes

2. Section 22 makes the annual value of buildings or lands appurtenant to them, of which you are the owner, chargeable under the head "Income from house property" (other than portions you occupy for your own business or profession).
   - Cited: Section 22 (Income-tax Act, 1961, PDF p. 90)
   - Quote: "shall be chargeable to income-tax under the head "Income from house property""
   - Verified: yes

3. Because the property is let, its annual value is determined under Section 23(1), generally the reasonably expected rent, or the actual rent received or receivable if that is higher. The nil annual value rule for self-occupied property in Section 23(2) does not apply where the house is actually let during the whole or any part of the previous year (Section 23(3)(a)).
   - Cited: Section 23(1)(a) (Income-tax Act, 1961, PDF p. 91); Section 23(1)(b) (Income-tax Act, 1961, PDF p. 91); Section 23(2) (Income-tax Act, 1961, PDF p. 91); Section 23(3)(a) (Income-tax Act, 1961, PDF p. 91)
   - Quote: "the house or part of the house is actually let during the whole or any part of the previous year"
   - Verified: yes

4. Yes, Section 24(b) allows a deduction for the amount of interest payable on borrowed capital where the property has been acquired, constructed, repaired, renewed or reconstructed with that capital. This applies to your housing loan on the property.
   - Cited: Section 24(b) (Income-tax Act, 1961, PDF p. 92)
   - Quote: "the amount of any interest payable on such capital"
   - Verified: yes

5. The Section 24(b) first proviso cap of thirty thousand rupees applies only to property referred to in Section 23(2) (self-occupied or unoccupied). Your property is let, so that proviso does not apply to it on the extracts provided, and the extracts do not state a separate cap for let property.
   - Cited: Section 24(b), first proviso (Income-tax Act, 1961, PDF p. 92); Section 23(3)(a) (Income-tax Act, 1961, PDF p. 91)
   - Quote: "in respect of property referred to in sub-section (2) of section 23"
   - Verified: yes

6. Interest payable for the period before the previous year of acquisition or construction is deducted under Section 24(b) in equal instalments over that previous year and the four following previous years, reduced by any part allowed under another provision.
   - Cited: Section 24(b), Explanation (Income-tax Act, 1961, PDF p. 92)
   - Quote: "shall be deducted under this clause in equal instalments for the said previous year"
   - Verified: yes

7. Sections 80EE and 80EEA also provide deductions for loan interest for individuals, but only if conditions are met, such as loan sanction dates, loan amount and value limits, and not owning any other residential house on the date of sanction. If interest is allowed under either section, it cannot be allowed under any other provision.
   - Cited: Section 80EE(4) (Income-tax Act, 1961, PDF p. 300); Section 80EEA(4) (Income-tax Act, 1961, PDF p. 301)
   - Quote: "deduction shall not be allowed in respect of such interest under any other provision of this Act"
   - Verified: yes

**Not covered by the text found:** The extracts do not state an overall cap on Section 24(b) interest deduction for let property, and the facts given (loan sanction date, loan amount, property value, other houses owned) are not enough to say whether Section 80EE or 80EEA would apply to you.

Screenshot: [screenshots/house-property.png](screenshots/house-property.png)

## 2. Tuition fees for children

**Question:** Is tuition fees paid for children deductible?

**Status:** answered. **Confidence:** medium (0.72: verified 1.00, retrieval 0.30, agreement 1.00, completeness 0.50). **Time:** search 151 ms, answer 5.4 s.

1. Yes, under Section 80C(2)(xvii), tuition fees paid to a university, college, school or other educational institution in India for the full-time education of the persons specified in sub-section (4) count towards the Section 80C deduction. Development fees, donations or payments of a similar nature are excluded.
   - Cited: Section 80C(2)(xvii) (Income-tax Act, 1961, PDF p. 283)
   - Quote: "as tuition fees (excluding any payment towards any development fees or donation or payment of similar nature)"
   - Verified: yes

2. Under Section 80C(4)(c), for an individual, the tuition fee deduction applies only to fees for any two children of that individual.
   - Cited: Section 80C(4)(c) (Income-tax Act, 1961, PDF p. 284)
   - Quote: "in the case of an individual, any two children of such individual"
   - Verified: yes

3. Section 80C(1) allows the deduction only to an individual or a Hindu undivided family. The deduction covers the amount paid in the previous year, and the aggregate of all Section 80C(2) sums is capped at one hundred and fifty thousand rupees.
   - Cited: Section 80C(1) (Income-tax Act, 1961, PDF p. 283)
   - Quote: "as does not exceed one hundred and fifty thousand rupees"
   - Verified: yes

**Not covered by the text found:** The extracts do not say whether a Hindu undivided family can claim tuition fees. Section 80C(4)(c) refers only to an individual and his children.

Screenshot: [screenshots/mobile-tuition-fees.png](screenshots/mobile-tuition-fees.png)

## 3. Penalty for not deducting TDS

**Question:** What is the penalty for not deducting TDS?

**Status:** answered. **Confidence:** high (0.86: verified 1.00, retrieval 0.79, agreement 1.00, completeness 0.50). **Time:** search 137 ms, answer 5.8 s.

1. Under Section 271C(1)(a), a person who fails to deduct the whole or any part of the tax as required under Chapter XVII-B is liable to a penalty equal to the amount of tax which they failed to deduct.
   - Cited: Section 271C(1)(a) (Income-tax Act, 1961, PDF p. 972); Section 271C(1) (Income-tax Act, 1961, PDF p. 972)
   - Quote: "deduct the whole or any part of the tax as required by or under the provisions of Chapter XVII-B"
   - Verified: yes

2. The penalty under Section 271C(1) is a sum equal to the amount of tax that the person failed to deduct (or pay or ensure payment of), so it is equal to the tax not deducted.
   - Cited: Section 271C(1) (Income-tax Act, 1961, PDF p. 972)
   - Quote: "shall be liable to pay, by way of penalty, a sum equal to the amount of tax which such person failed to deduct or pay or ensure payment of"
   - Verified: yes

3. Under Section 271C(2), the penalty is imposed by the Joint Commissioner, but under the first proviso, any penalty on or after 1 April 2025 is imposed by the Assessing Officer.
   - Cited: Section 271C(2) (Income-tax Act, 1961, PDF p. 972); Section 271C(2), first proviso (Income-tax Act, 1961, PDF p. 972)
   - Quote: "Provided that any penalty under sub-section (1) on or after the 1st day of April, 2025, shall be imposed by the Assessing Officer."
   - Verified: yes

**Not covered by the text found:** The extracts do not state any exceptions or defences to the Section 271C penalty, nor the separate consequences of non-deduction such as interest or disallowance of expenditure, apart from the penalty itself. Penalty for failure to collect tax at source (Section 271CA) and for late or incorrect TDS statements (Section 271H) are different provisions.

Screenshot: [screenshots/tds-penalty.png](screenshots/tds-penalty.png)

## 4. Out of scope: GST rate (refused)

**Question:** What is the GST rate on restaurant services?

**Status:** refused. **Time:** search 141 ms, answer 3.8 s.

The Act's text that was found does not support an answer to this question.

**Not covered by the text found:** The question asks for the GST rate on restaurant services. The extracts are from the Income-tax Act, 1961 and do not deal with GST or any rate applicable to restaurant services. The only mention of restaurants is in the Eleventh Schedule's Explanation to item 22 (office machines and apparatus), which is unrelated to GST rates.

Screenshot: [screenshots/refusal-gst.png](screenshots/refusal-gst.png)
