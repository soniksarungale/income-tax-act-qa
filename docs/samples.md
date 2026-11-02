# Sample questions and answers

Real outputs of the deployed app (https://taxqa.soniksarungale.com) on 3 November 2026,
provider `claude-cli`, model claude-sonnet-5-5. Each was asked once through the web page; nothing
was re-run or edited. Answers vary slightly between runs because the CLI has no temperature setting.

## 1. Rented house: 30% deduction and loan interest (the brief's example)

**Question:** I own a residential property that I have rented out. Can I claim a 30% deduction on the annual value of the property? I also have a housing loan on this property. Can I claim a deduction for the interest paid on the loan? Which sections of the Income-tax Act apply?

**Status:** partial. **Confidence:** high (0.79: verified 0.80, retrieval 0.80, agreement 1.00, completeness 0.50). **Time:** search 225 ms, answer 9.6 s.

1. Yes, Section 24(a) allows a deduction of thirty per cent of the annual value when computing income chargeable under the head "Income from house property". Since your property is let out, this applies to it.
   - Cited: Section 24 (Income-tax Act, 1961, PDF p. 92); Section 24(a) (Income-tax Act, 1961, PDF p. 92)
   - Quote: "(a) a sum equal to thirty per cent of the annual value;"
   - Verified: yes

2. Section 22 makes the annual value of a building you own chargeable under the head "Income from house property", and Section 23(1) determines that annual value for a let property, for example by reference to the actual rent received or receivable where it exceeds the reasonably expected rent.
   - Cited: Section 22 (Income-tax Act, 1961, PDF p. 90); Section 23(1)(b) (Income-tax Act, 1961, PDF p. 91)
   - Quote: "shall be chargeable to income-tax under the head "Income from house property""
   - Verified: yes

3. Yes, Section 24(b) allows a deduction for the interest payable on borrowed capital where the property has been acquired, constructed, repaired, renewed or reconstructed with that capital.
   - Cited: Section 24(b) (Income-tax Act, 1961, PDF p. 92)
   - Quote: "where the property has been acquired, constructed, repaired, renewed or reconstructed with borrowed capital"
   - Verified: yes

4. The first proviso to Section 24(b) applies a cap of thirty thousand rupees only to property referred to in Section 23(2), which is a house you occupy for your own residence or cannot actually occupy. Section 23(3)(a) says Section 23(2) does not apply if the house is actually let during the whole or any part of the previous year. Because your property is rented out, that cap therefore does not appear to apply to it on the extracts given.
   - Cited: Section 24(b), first proviso (Income-tax Act, 1961, PDF p. 92); Section 23(2) (Income-tax Act, 1961, PDF p. 91); Section 23(3)(a) (Income-tax Act, 1961, PDF p. 91)
   - Quote: "The provisions of sub-section (2) shall not apply if"
   - Verified: no, quote not found in the cited text

5. For interest payable on capital borrowed for the period before the previous year in which the property was acquired or constructed, the Explanation to Section 24(b) provides that it is deducted in equal instalments for that previous year and the four immediately succeeding previous years.
   - Cited: Section 24(b), Explanation (Income-tax Act, 1961, PDF p. 92)
   - Quote: "shall be deducted under this clause in equal instalments for the said previous year and for each of the four immediately succeeding previous years"
   - Verified: yes

**Not covered by the text found:** The extracts do not state any overall cap on interest deduction for a let-out property, and they do not state your actual annual value or interest amount. Sections 80EE and 80EEA also allow interest deductions for first-time home buyers, subject to conditions such as loan sanction dates and property value limits. Whether either applies depends on facts you have not given, such as when the loan was sanctioned, the loan amount and the property value. Section 80EE(4) and Section 80EEA(4) also bar a second deduction for the same interest under any other provision.

Screenshot: [screenshots/house-property.png](screenshots/house-property.png)

Note on claim 4: the quoted words are the opening of section 23(3) ("The provisions of
sub-section (2) shall not apply if"). They reached the model as the context line of the
23(3)(a) extract, not as that extract's own text, and the verifier only accepts quotes from
the cited text itself. So the point is shown as not verified, and the answer as partly
answered, even though the words are in the Act. This is the check being strict by design:
a quote that cannot be matched to the cited text is flagged, never silently accepted.

## 2. Tuition fees for children

**Question:** Is tuition fees paid for children deductible?

**Status:** answered. **Confidence:** high (0.79: verified 1.00, retrieval 0.30, agreement 1.00, completeness 1.00). **Time:** search 134 ms, answer 7.4 s.

1. Yes, under Section 80C(2)(xvii), tuition fees paid to a university, college, school or other educational institution in India for full-time education of the persons specified in Section 80C(4) are a sum that qualifies for deduction under Section 80C(1), provided the assessee is an individual (or HUF, per Section 80C(1)) and the payment is made in the previous year.
   - Cited: Section 80C(2)(xvii) (Income-tax Act, 1961, PDF p. 283); Section 80C(1) (Income-tax Act, 1961, PDF p. 283)
   - Quote: "as tuition fees (excluding any payment towards any development fees or donation or payment of similar nature)"
   - Verified: yes

2. Under Section 80C(4)(c), for tuition fees the covered persons, in the case of an individual, are any two children of that individual, so the deduction is limited to fees for two children.
   - Cited: Section 80C(4)(c) (Income-tax Act, 1961, PDF p. 284)
   - Quote: "in the case of an individual, any two children of such individual"
   - Verified: yes

3. Section 80C(2)(xvii) excludes development fees, donations or payments of a similar nature, so only genuine tuition fees qualify, whether paid at admission or thereafter.
   - Cited: Section 80C(2)(xvii) (Income-tax Act, 1961, PDF p. 283)
   - Quote: "whether at the time of admission or thereafter"
   - Verified: yes

4. The fees must be for full-time education at an institution situated within India, and the tuition fees count toward the overall Section 80C(1) ceiling of one hundred and fifty thousand rupees, aggregated with other eligible sums.
   - Cited: Section 80C(2)(xvii) (Income-tax Act, 1961, PDF p. 283); Section 80C(1) (Income-tax Act, 1961, PDF p. 283)
   - Quote: "does not exceed one hundred and fifty thousand rupees"
   - Verified: yes

Screenshot: [screenshots/tuition-fees.png](screenshots/tuition-fees.png)

## 3. Penalty for not deducting TDS

**Question:** What is the penalty for not deducting TDS?

**Status:** answered. **Confidence:** high (0.85: verified 1.00, retrieval 0.76, agreement 1.00, completeness 0.50). **Time:** search 124 ms, answer 6.4 s.

1. Under Section 271C(1)(a), a person who fails to deduct the whole or any part of the tax as required under Chapter XVII-B is liable to a penalty equal to the amount of tax which he failed to deduct.
   - Cited: Section 271C(1)(a) (Income-tax Act, 1961, PDF p. 972); Section 271C(1) (Income-tax Act, 1961, PDF p. 972)
   - Quote: "such person shall be liable to pay, by way of penalty, a sum equal to the amount of tax which such person failed to deduct or pay or ensure payment of, as aforesaid."
   - Verified: yes

2. Section 271C(1)(b) applies the same penalty (equal to the tax not paid) where a person fails to pay or ensure payment of tax under specified provisions, such as the proviso to section 194B or sub-section (2) of section 194BA.
   - Cited: Section 271C(1)(b) (Income-tax Act, 1961, PDF p. 972); Section 271C(1) (Income-tax Act, 1961, PDF p. 972)
   - Quote: "pay or ensure payment of, the whole or any part of the tax as required by or under"
   - Verified: yes

3. Under Section 271C(2) and its first proviso, the penalty is imposed by the Joint Commissioner, but on or after 1 April 2025 it is imposed by the Assessing Officer.
   - Cited: Section 271C(2) (Income-tax Act, 1961, PDF p. 972); Section 271C(2), first proviso (Income-tax Act, 1961, PDF p. 972)
   - Quote: "shall be imposed by the Assessing Officer."
   - Verified: yes

4. Separately, Section 271H(1) and (2) allows a penalty of not less than ten thousand rupees and up to one lakh rupees for failing to deliver the TDS statement within the prescribed time under section 200(3) or for furnishing incorrect information in it. This is a different default from failing to deduct tax.
   - Cited: Section 271H(1) (Income-tax Act, 1961, PDF p. 987); Section 271H(1)(a) (Income-tax Act, 1961, PDF p. 987); Section 271H(1)(b) (Income-tax Act, 1961, PDF p. 987); Section 271H(2) (Income-tax Act, 1961, PDF p. 987)
   - Quote: "shall not be less than ten thousand rupees but which may extend to one lakh rupees"
   - Verified: yes

**Not covered by the text found:** The extracts do not state any exceptions or defences to the Section 271C penalty, nor the procedure for imposing it. They also do not cover interest or disallowance consequences of non-deduction.

Screenshot: [screenshots/tds-penalty.png](screenshots/tds-penalty.png)

## 4. Out of scope: GST rate (refused)

**Question:** What is the GST rate on restaurant services?

**Status:** refused. **Time:** search 123 ms, answer 11.0 s.

The Act's text that was found does not support an answer to this question.

**Not covered by the text found:** The question asks about the GST rate on restaurant services. The extracts are from the Income-tax Act, 1961 and do not deal with GST or any rate applicable to restaurant services.

Screenshot: [screenshots/refusal-gst.png](screenshots/refusal-gst.png)
