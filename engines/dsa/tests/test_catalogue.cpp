#include "internpath/catalogue/internship_catalogue.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <string>

using internpath::catalogue::InternshipCatalogue;
using internpath::catalogue::InternshipRecord;

int main() {
    InternshipCatalogue catalogue;
    assert(catalogue.empty() && catalogue.size() == 0);

    // 1. Insert several internships
    InternshipRecord r1{"INT-101", "Embedded Systems Intern", "Tesla", "2026-11-15", "Palo Alto, CA", 600000};
    InternshipRecord r2{"INT-102", "Robotics Software Intern", "Boston Dynamics", "2026-11-30", "Waltham, MA", 650000};
    InternshipRecord r3{"INT-103", "C++ Systems Intern", "Qualcomm", "2026-11-30", "San Diego, CA", 550000}; // Same deadline as INT-102!
    InternshipRecord r4{"INT-104", "RTOS Kernel Intern", "Apple", "2026-12-15", "Cupertino, CA", 700000};
    InternshipRecord r5{"INT-105", "Firmware Engineer Intern", "NVIDIA", "2026-10-31", "Santa Clara, CA", 680000};

    assert(catalogue.add_internship(r1));
    assert(catalogue.add_internship(r2));
    assert(catalogue.add_internship(r3));
    assert(catalogue.add_internship(r4));
    assert(catalogue.add_internship(r5));
    assert(catalogue.size() == 5);
    assert(catalogue.verify_synchronization());

    // 6a. Reject duplicate ID insertion
    InternshipRecord dup{"INT-101", "Different Title", "Different Company", "2026-12-01", "Remote", 500000};
    assert(!catalogue.add_internship(dup));
    assert(catalogue.size() == 5);
    assert(catalogue.verify_synchronization());

    // 2. Lookup internship by ID (O(1) Hash Table lookup)
    auto found102 = catalogue.find_by_id("INT-102");
    assert(found102 != nullptr);
    assert(found102->company_name == "Boston Dynamics");
    assert(found102->role_title == "Robotics Software Intern");
    assert(found102->deadline == "2026-11-30");

    auto found_missing = catalogue.find_by_id("INT-999");
    assert(found_missing == nullptr);

    // 3. Query internships closing within a selected date range (AVL Tree Range Query)
    // Query November 2026: [2026-11-01, 2026-11-30]
    // Expect: INT-101 (Nov 15), INT-102 (Nov 30), INT-103 (Nov 30) -> 3 records sorted by deadline!
    auto nov_internships = catalogue.query_by_deadline_range("2026-11-01", "2026-11-30");
    assert(nov_internships.size() == 3);
    assert(nov_internships[0]->id == "INT-101" && nov_internships[0]->deadline == "2026-11-15");
    // Due to composite key (deadline, id), INT-102 and INT-103 both appear in sorted order:
    assert(nov_internships[1]->id == "INT-102" && nov_internships[1]->deadline == "2026-11-30");
    assert(nov_internships[2]->id == "INT-103" && nov_internships[2]->deadline == "2026-11-30");

    // Single-day range: exactly on 2026-11-30
    auto nov30_only = catalogue.query_by_deadline_range("2026-11-30", "2026-11-30");
    assert(nov30_only.size() == 2);
    assert(nov30_only[0]->id == "INT-102" && nov30_only[1]->id == "INT-103");

    // Range with zero results
    auto early_range = catalogue.query_by_deadline_range("2026-01-01", "2026-05-01");
    assert(early_range.empty());

    // 4. Update a deadline and verify both indexes stay synchronized
    // Move INT-103 from 2026-11-30 to 2026-10-25
    assert(catalogue.update_deadline("INT-103", "2026-10-25"));
    assert(catalogue.verify_synchronization());

    // Verify lookup by ID reflects new deadline
    auto updated103 = catalogue.find_by_id("INT-103");
    assert(updated103 && updated103->deadline == "2026-10-25");

    // Verify deadline range query on November no longer contains INT-103 (now has 2: INT-101, INT-102)
    auto nov_after_update = catalogue.query_by_deadline_range("2026-11-01", "2026-11-30");
    assert(nov_after_update.size() == 2);
    assert(nov_after_update[0]->id == "INT-101");
    assert(nov_after_update[1]->id == "INT-102");

    // Verify October query now includes INT-103 and INT-105
    auto oct_query = catalogue.query_by_deadline_range("2026-10-01", "2026-10-31");
    assert(oct_query.size() == 2);
    assert(oct_query[0]->id == "INT-103" && oct_query[0]->deadline == "2026-10-25");
    assert(oct_query[1]->id == "INT-105" && oct_query[1]->deadline == "2026-10-31");

    // 6b. Safely handle invalid updates
    assert(!catalogue.update_deadline("NON_EXISTENT_ID", "2026-12-01"));
    assert(!catalogue.update_deadline("INT-101", "")); // Empty deadline
    assert(catalogue.verify_synchronization());

    // 5. Delete an internship and verify absence in both indexes
    assert(catalogue.remove_internship("INT-101"));
    assert(!catalogue.contains("INT-101"));
    assert(catalogue.find_by_id("INT-101") == nullptr);
    assert(catalogue.size() == 4);
    assert(catalogue.verify_synchronization());

    // Nov query should now only contain INT-102
    auto nov_after_delete = catalogue.query_by_deadline_range("2026-11-01", "2026-11-30");
    assert(nov_after_delete.size() == 1);
    assert(nov_after_delete[0]->id == "INT-102");

    // Remove remaining
    assert(catalogue.remove_internship("INT-102"));
    assert(catalogue.remove_internship("INT-103"));
    assert(catalogue.remove_internship("INT-104"));
    assert(catalogue.remove_internship("INT-105"));
    assert(catalogue.empty() && catalogue.size() == 0);
    assert(catalogue.verify_synchronization());

    std::cout << "InternshipCatalogue tests passed\n";
    return 0;
}
