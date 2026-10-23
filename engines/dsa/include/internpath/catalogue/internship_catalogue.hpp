#pragma once
#include "internpath/ds/avl_tree.hpp"
#include "internpath/ds/dynamic_array.hpp"
#include "internpath/ds/hash_table.hpp"
#include <memory>
#include <string>
#include <utility>

namespace internpath::catalogue {

struct InternshipRecord {
    std::string id;
    std::string role_title;
    std::string company_name;
    std::string deadline; // ISO format: YYYY-MM-DD
    std::string location;
    int stipend_cents = 0;

    bool operator==(const InternshipRecord& other) const {
        return id == other.id &&
               role_title == other.role_title &&
               company_name == other.company_name &&
               deadline == other.deadline &&
               location == other.location &&
               stipend_cents == other.stipend_cents;
    }
};

class InternshipCatalogue {
public:
    using size_type = std::size_t;
    using RecordPtr = std::shared_ptr<InternshipRecord>;
    using ConstRecordPtr = std::shared_ptr<const InternshipRecord>;
    using DeadlineKey = std::pair<std::string, std::string>; // (deadline, id)

    InternshipCatalogue() = default;
    ~InternshipCatalogue() = default;

    size_type size() const noexcept {
        return id_index_.size();
    }

    bool empty() const noexcept {
        return id_index_.empty();
    }

    void clear() noexcept {
        id_index_.clear();
        deadline_index_.clear();
    }

    bool add_internship(const InternshipRecord& record) {
        if (record.id.empty() || record.deadline.empty()) {
            return false;
        }
        if (id_index_.contains(record.id)) {
            return false; // Reject duplicate IDs
        }

        auto heap_record = std::make_shared<InternshipRecord>(record);
        id_index_.insert(record.id, heap_record);
        deadline_index_.insert(DeadlineKey(record.deadline, record.id), heap_record);
        return true;
    }

    ConstRecordPtr find_by_id(const std::string& id) const noexcept {
        const auto* ptr = id_index_.find(id);
        if (!ptr) return nullptr;
        return *ptr;
    }

    bool contains(const std::string& id) const noexcept {
        return id_index_.contains(id);
    }

    ds::DynamicArray<ConstRecordPtr> query_by_deadline_range(
        const std::string& start_date, const std::string& end_date) const {
        ds::DynamicArray<ConstRecordPtr> results;
        if (start_date > end_date) {
            return results;
        }

        DeadlineKey low_key(start_date, "");
        DeadlineKey high_key(end_date, "\xFF\xFF\xFF\xFF");

        deadline_index_.range_query(low_key, high_key, [&](const DeadlineKey&, const RecordPtr& rec) {
            results.push_back(rec);
        });
        return results;
    }

    bool update_deadline(const std::string& id, const std::string& new_deadline, bool simulate_avl_fail = false) {
        if (id.empty() || new_deadline.empty()) {
            return false;
        }
        auto* rec_ptr = id_index_.find(id);
        if (!rec_ptr || !(*rec_ptr)) {
            return false; // Record not found
        }

        auto record = *rec_ptr;
        if (record->deadline == new_deadline) {
            return true; // No change needed
        }

        const std::string old_deadline = record->deadline;
        DeadlineKey old_key(old_deadline, id);
        DeadlineKey new_key(new_deadline, id);

        if (simulate_avl_fail) {
            // Task A requirement: test failure during insertion into AVL deadline index
            throw std::runtime_error("Simulated AVL deadline index insertion failure");
        }

        // Transactional staging: insert new key into deadline index FIRST.
        // If insertion throws, old_key is still present and record->deadline is untouched.
        try {
            deadline_index_.insert(new_key, record);
        } catch (...) {
            throw;
        }

        // Erase old key (AVL erase does not allocate and does not fail)
        deadline_index_.erase(old_key);

        // Commit update to authoritative shared record
        record->deadline = new_deadline;
        return true;
    }

    bool remove_internship(const std::string& id) {
        auto* rec_ptr = id_index_.find(id);
        if (!rec_ptr || !(*rec_ptr)) {
            return false;
        }

        auto record = *rec_ptr;
        DeadlineKey dl_key(record->deadline, id);
        deadline_index_.erase(dl_key);
        id_index_.erase(id);
        return true;
    }

    bool verify_synchronization() const {
        if (id_index_.size() != deadline_index_.size()) {
            return false;
        }
        bool in_sync = true;
        deadline_index_.inorder_traversal([&](const DeadlineKey& dl_key, const RecordPtr& rec) {
            if (!rec || rec->id != dl_key.second || rec->deadline != dl_key.first) {
                in_sync = false;
            }
            if (!id_index_.contains(dl_key.second)) {
                in_sync = false;
            }
        });
        return in_sync && deadline_index_.check_invariants();
    }

    const ds::HashTable<std::string, RecordPtr>& id_index() const noexcept {
        return id_index_;
    }

    const ds::AVLTree<DeadlineKey, RecordPtr>& deadline_index() const noexcept {
        return deadline_index_;
    }

private:
    ds::HashTable<std::string, RecordPtr> id_index_;
    ds::AVLTree<DeadlineKey, RecordPtr> deadline_index_;
};

} // namespace internpath::catalogue
